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
import streamlit.components.v1 as components
import pyvis.network as net
import logging
from typing import Dict, List, Any
import db_utils as dbm
import context_utils as cu
import funcUtils as fu

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

def create_relationship_graph(relationship_data: Dict[str, Any]) -> net.Network:
    """
    Create a Pyvis network diagram of the relationship tree.
    
    Args:
        relationship_data: Dictionary containing relationship data
        
    Returns:
        pyvis.network.Network: The generated relationship network
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
    
    # Configure physics and styling
    graph.set_options("""
    {
      "physics": {
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "centralGravity": 0.01,
          "springLength": 100,
          "springConstant": 0.08
        },
        "maxVelocity": 50,
        "solver": "forceAtlas2Based",
        "timestep": 0.35,
        "stabilization": {
          "iterations": 150
        }
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
          "type": "continuous"
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
    
    # Add center node
    center_id = str(center.get('id', 'unknown'))
    center_name = center.get('name', 'Unknown')
    center_label = f"{center_id}: {center_name}"
    
    graph.add_node(
        center_id,
        label=center_label,
        title=f"Center Member: {center_name}",
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
        graph.add_node(
            family_member_id,
            label=family_member_label,
            title=f"Family Member: {family_member_name}\nRelation: {relation_type}",
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
            title=f"Relation: {relation_type}",
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
    # Sidebar --- from here
    with st.sidebar:
        if st.session_state.user_state != dbm.User_State['p_admin']:
            # Hide the default navigation for non-padmin users
            st.markdown("""
            <style>
            [data-testid="stSidebarNav"] {
                display: none !important;
                }
            </style>""", unsafe_allow_html=True)
        
        if 'user_email' in st.session_state and st.session_state.user_email:
            st.markdown(
                f"<div style='background-color: #2e7d32; padding: 0.5rem; border-radius: 0.5rem; margin-bottom: 1rem;'>"
                f"<p style='color: white; margin: 0; font-weight: bold; text-align: center;'>{st.session_state.user_email}</p>"
                "</div>",
                unsafe_allow_html=True)
            cu.update_context({'email_user': st.session_state.user_email})
        
        if st.session_state.user_state != dbm.User_State['p_admin']:
            st.subheader(f"{UI_TEXTS['navigation']}")
            st.page_link("fTrees.py", label="Home", icon="🏠")
            # st.page_link("pages/5_ftpe.py", label="FamilyTreePE", icon="📊")
            if st.session_state.user_state == dbm.User_State['f_admin']:
                st.page_link("pages/2_famMgmt.py", label="Family Management", icon="🌲")
                st.page_link("pages/8_caseMgmt.py", label="Case Management", icon="📋")
                st.page_link("pages/9_birthday.py", label="Birthday", icon="🎂")
            st.page_link("pages/6_show_3G.py", label="Show 3 Generations", icon="👥")
            st.page_link("pages/3_csv_editor.py", label="CSV Editor", icon="🔧")
            st.page_link("pages/4_json_editor.py", label="JSON Editor", icon="🪛")
            
        # Add logout button at the bottom
        if st.button(f"{UI_TEXTS['logout']}", type="primary", use_container_width=True, key="show_3g_logout"):
            # Log logout activity
            if 'user_email' in st.session_state and st.session_state.user_email:
                fu.log_activity(st.session_state.user_email, 'logout')
            st.session_state.authenticated = False
            st.session_state.user_email = None
            st.rerun()
    
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
            components.html(graph_html, height=600, scrolling=True)
            
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

# Initialize session state and UI_TEXTS
if 'app_context' not in st.session_state:
    cu.init_session_state()
cu.apply_ui_preferences()

# Get UI_TEXTS with a fallback to English if needed
try:
    UI_TEXTS = st.session_state.ui_context[st.session_state.app_context.get('language', 'US')]
except (KeyError, AttributeError):
    # Fallback to English if there's any issue
    UI_TEXTS = st.session_state.ui_context['US']

# Check authentication
if not st.session_state.get('authenticated', False):
    st.switch_page("fTrees.py")
else:
    if 'app_context' not in st.session_state:
        st.session_state.app_context = cu.init_context()
    main()