"""
This script displays a relationship tree centered around a given 
member ID via streamlit.
It shows :
- the center member (id and name from dbm.db_tables['members'] table), 
- their related family members (id and name from dbm.db_tables['members'] table), 
- and corresponding relation types (on the label of edges) 
- draw a graph visualization using pyvis.
"""

import streamlit as st
import pyvis.network as net
import logging
from typing import Dict, List, Any
import db_utils as dbm
import context_utils as cu
import funcUtils as fu
from graph_text import center_popup, generation_level, related_popup, relation_popup
from nav import render_sidebar, require_role

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_relationship_data(member_id: int, relations: List[str]) -> Dict[str, Any]:
    """
    Retrieve relationship data for a given member ID.
    
    Args:
        member_id: The ID of the center member
        relations: List of relations to be displayed
        
    Returns:
        Dict containing:
            - center: The center member
            - relationships: List of relationships where the member is involved
            - family_members: List of family members with their relationship info
    """
    try:
        if relations is None or len(relations) == 0:
            # Default to all relations
            relations = list(dbm.Relation_Type.values())
        # Get the center member
        center = dbm.get_member(member_id)
        if not center:
            st.error(f"❌ No member found with ID: {member_id}")
            return {}
            
        # Get all relationships where this member is either member_id or partner_id
        relationships = dbm.get_relations_by_id(member_id)
        
        # Process relationships to get family member information
        family_members = []
        for rel in relationships:
            # Determine if the current member is member_id or partner_id
            if rel['member_id'] == member_id:
                partner_id = rel['partner_id']
                relation_type = rel['relation']
            else:
                partner_id = rel['member_id']
                # Reverse the relation for display (e.g., "spouse" remains the same, but "parent" becomes "child")
                relation_type = get_inverse_relation(rel['relation'])
            if relation_type not in relations:
                continue

            # Get partner details
            partner = dbm.get_member(partner_id)
            if partner:
                family_members.append({
                    'id': partner_id,
                    'name': partner.get('name', 'Unknown'),
                    'gen_order': partner.get('gen_order'),
                    'relation': relation_type,
                    'relation_id': rel.get('id', ''),  # Add relation_id from the relations table
                    'join_date': rel.get('join_date', ''),
                    'end_date': rel.get('end_date', '')
                })
        
        return {
            'center': center,
            'relationships': relationships,
            'family_members': family_members
        }
        
    except Exception as e:
        fu.show_user_error("❌ Error retrieving relationship data", e)
        logger.exception(f"Error in {fu.get_function_name()}")
        return {}

def get_inverse_relation(relation_type: str) -> str:
    """
    Get the inverse of a relationship type.
    
    Args:
        relation_type: The original relation type (e.g., 'parent', 'spouse')
        
    Returns:
        The inverse relation type (e.g., 'child' for 'parent', 'spouse' for 'spouse')
    """
    relation_map = {
        'parent': dbm.Relation_Type['child'],
        'child': dbm.Relation_Type['parent'],
        'parent adopted within family': dbm.Relation_Type['child ai'],
        'child adopted within family': dbm.Relation_Type['parent ai'],
        'parent adopted from another family': dbm.Relation_Type['child ao'],
        'child adopted from another family': dbm.Relation_Type['parent ao'],
        'parent step': dbm.Relation_Type['child step'],
        'child step': dbm.Relation_Type['parent step']
    }
    relation = relation_map.get(relation_type.lower(), relation_type)
    return relation

def relation_row_offset(relation_type: str) -> int:
    """Relative row when a person has no stored generation."""
    text = str(relation_type or "").lower()
    if text.startswith("parent"):
        return -1
    if text.startswith("child"):
        return 1
    return 0

def create_relationship_graph(relationship_data: Dict[str, Any]) -> net.Network:
    """
    Create a Pyvis network of the relationships.

    Each generation is one horizontal row, top to bottom, using the same
    hierarchical layout as the three-generation graph. Physics is off so a
    person stays on that row.
    """
    # Create a new network
    graph = net.Network(
        height="600px",
        width="100%",
        bgcolor='white',
        font_color='black',
        directed=True,
        notebook=False
    )

    # Same top-down rows as the three-generation graph. Edge labels stay gray.
    graph.set_options("""
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "UD",
          "sortMethod": "directed",
          "levelSeparation": 150,
          "nodeSpacing": 180,
          "treeSpacing": 200,
          "shakeTowards": "roots"
        }
      },
      "physics": {
        "enabled": false
      },
      "nodes": {
        "borderWidth": 2,
        "borderWidthSelected": 3,
        "font": {
          "size": 14,
          "face": "Arial",
          "color": "black"
        }
      },
      "edges": {
        "arrows": {
          "to": {
            "enabled": true,
            "scaleFactor": 0.8
          }
        },
        "color": {
          "inherit": true
        },
        "smooth": {
          "type": "cubicBezier",
          "forceDirection": "vertical",
          "roundness": 0.4
        },
        "font": {
          "size": 12,
          "align": "center",
          "color": "#708090"
        }
      }
    }
    """)
    
    center = relationship_data.get('center', {})
    family_members = relationship_data.get('family_members', [])
    center_level = generation_level(center, 0)
    
    # Add center node
    center_id = str(center.get('id', 'unknown'))
    center_name = center.get('name', 'Unknown')
    center_label = f"{center_id}: {center_name}"
    
    graph.add_node(
        center_id,
        label=center_label,
        title=center_popup(center_name),
        level=center_level,
        color={
            'background': '#ffffe0',  # Light yellow for center
            'border': '#ffd700'       # Gold border
        },
        shape='ellipse',
        size=25,
        border_width=3,
        font={'size': 16, 'bold': True}
    )
    
    # Add family member nodes and edges
    for family_member in family_members:
        family_member_id = str(family_member['id'])
        family_member_name = family_member['name']
        relation_type = family_member['relation']
        
        # Create family member node
        family_member_label = f"{family_member_id}: {family_member_name}"
        fallback = center_level + relation_row_offset(relation_type)
        graph.add_node(
            family_member_id,
            label=family_member_label,
            title=related_popup(family_member_name, relation_type),
            level=generation_level(family_member, fallback),
            color={
                'background': '#f0f8ff',  # Light blue background
                'border': '#4682b4'      # Steel blue border
            },
            shape='box',
            size=20,
            border_width=2
        )
        
        # Add edge with relation type
        graph.add_edge(
            center_id,
            family_member_id,
            label=relation_type,
            title=relation_popup(relation_type),
            color='#a9a9a9'
        )
    
    return graph

def main():
    """
    Main function to render the Streamlit app.
    """
    global UI_TEXTS
    
    st.set_page_config(
        page_title="Member Relationship Visualization",
        page_icon="👨‍👩‍👧‍👦",
        layout="wide"
    )
    render_sidebar()

    # Main page --- from here
    st.header(f"{UI_TEXTS['family']} {UI_TEXTS['member']} {UI_TEXTS['relation']} {UI_TEXTS['visualization']}")
    st.subheader(f"{UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['member']} {UI_TEXTS['relation']}")
    
    # Get member ID from URL parameters or input
    member_id = int(st.query_params.get('id', 0))
    
    # Member ID input
    col1, col2 = st.columns([1, 3])
    with col1:
        member_id = st.number_input(
            f"{UI_TEXTS['enter']} {UI_TEXTS['member']} {UI_TEXTS['id']}",
            min_value=0,
            value=member_id if member_id > 0 else 0,
            step=1
        )
    with col2:
        relations = st.multiselect(
            f"{UI_TEXTS['select']} {UI_TEXTS['relation_type']}",
            dbm.Relation_Type.values(),
            default=dbm.Relation_Type['parent'],
            help=f"{UI_TEXTS['select']} {UI_TEXTS['multiple']} {UI_TEXTS['relation_type']}"
        )
    
    if st.button(f"{UI_TEXTS['submit']}", type="primary") or member_id > 0:
        with st.spinner(f"{UI_TEXTS['search']} {UI_TEXTS['relation']} {UI_TEXTS['in_progress']}..."):
            # Get relationship data
            relationship_data = get_relationship_data(member_id, relations)
            
            if not relationship_data:
                st.warning(f"⚠️ {fu.get_function_name()} {UI_TEXTS['relation']} {UI_TEXTS['not_found']}: {member_id}")
                return
                
            # Display the member name as a header
            st.subheader(f"{UI_TEXTS['member']} {UI_TEXTS['name']}: {relationship_data['center'].get('name', 'Unknown')}")
            
            # Display the graph
            graph = create_relationship_graph(relationship_data)
            graph_html = graph.generate_html()
            # st.iframe always shows a scrollbar when the graph is taller than the frame.
            st.iframe(graph_html, width="stretch", height=600, alt="Relationship graph")
            
            # Create a container for relationship details below the graph
            with st.container():
                st.subheader(f"{UI_TEXTS['relation']} {UI_TEXTS['details']}")
                if not relationship_data['family_members']:
                    st.info(f"{UI_TEXTS['relation']} {UI_TEXTS['not_found']}")
                else:
                    # Create columns for better organization of partner details
                    cols = st.columns(2)  # 2 columns for partner details
                    
                    for i, partner in enumerate(relationship_data['family_members']):
                        # Alternate between columns for better use of space
                        with cols[i % 2]:
                            with st.expander(f"{partner['name']} (ID: {partner['id']})"):
                                st.markdown(f"**Relation ID:** {partner.get('relation_id', 'N/A')}")
                                st.markdown(f"**Relation:** {partner['relation'].title()}")
                                if partner.get('join_date'):
                                    st.markdown(f"**Since:** {partner['join_date']}")
                                if partner.get('end_date'):
                                    st.markdown(f"**Ended:** {partner['end_date']}")
                            st.markdown("---")

# Streamlit runs this file as __main__. Importing it for tests does not draw the page.
if __name__ == "__main__":
    if 'app_context' not in st.session_state:
        cu.init_session_state()
    cu.apply_ui_preferences()

    UI_TEXTS = fu.session_texts()

    if not st.session_state.get('authenticated', False):
        st.switch_page("fTrees.py")
    else:
        require_role(
            dbm.User_State['p_admin'],
            dbm.User_State['f_admin'],
            dbm.User_State['f_member'],
        )
        if 'app_context' not in st.session_state:
            st.session_state.app_context = cu.init_context()
        main()