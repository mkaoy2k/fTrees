"""
Family Tree Visualization - 

To draw a graph of a family tree upto 7 generations, i.e.
up to 3 generations and down to 3 generations, given a member ID.

This script displays a family tree centered around a given member ID.
It shows the member, his/her parents, grandparents, children, 
and grandchildren in a graph visualization using Pyvis.
"""

import streamlit as st
import pyvis.network as net
import logging
from typing import Dict, Any
from datetime import datetime
from dotenv import load_dotenv
import context_utils as cu
import funcUtils as fu

# Import database utilities
import db_utils as dbm
from fTrees import UI_TEXTS
from graph_layout import spread_nodes_across_iframe
from graph_text import generation_level, member_popup
from nav import render_sidebar, require_role

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_family_members(member_id: int) -> Dict[str, Any]:
    """
    Retrieve family members for a given member ID (3 generations).
    
    Args:
        member_id: The ID of the center member
        
    Returns:
        Dict containing:
            - center: The center member
            - parents: List of parents
            - children: List of children
            - grandparents: List of grandparents
            - grandchildren: List of grandchildren
    """
    try:
        # Get the center member
        center = dbm.get_member(member_id)
        if not center:
            st.error(f"❌ No member found with ID: {member_id}")
            return {}
            
        # Initialize result dictionary
        result = {
            'center': center,
            'parents': [],
            'children': [],
            'grandparents': [],
            'grandchildren': []
        }
        
        # Read parents and grandparents. Viewing the graph does not write relations.
        result['parents'] = dbm.get_parents(member_id)
        for parent in result['parents']:
            for grandparent in dbm.get_parents(parent['id']):
                if grandparent and grandparent not in result['grandparents']:
                    result['grandparents'].append(grandparent)

        result['children'] = dbm.get_children(member_id)
        for child in result['children']:
            for grandchild in dbm.get_children(child['id']):
                if grandchild and grandchild not in result['grandchildren']:
                    result['grandchildren'].append(grandchild)

        return result
        
    except Exception as e:
        fu.show_user_error("❌ Error fetching family members", e)
        logger.exception("Error in get_family_members")
        return {}


def create_family_graph(family_data: Dict[str, Any], height: int = 12, width: int = 15) -> net.Network:
    """
    Create a Pyvis network of the family tree.

    Each generation is one horizontal row. Smaller generation numbers sit
    above larger ones. Physics is off so a person stays on that row.
    After vis.js orders each row, the embedded script spreads the rows
    across the iframe width and height. When the labels would overlap, the
    tree is scaled down, keeping the same shape as the iframe so neither
    axis is left empty.

    Args:
        family_data: Dictionary containing family members data
        height: Height multiplier for the iframe (default: 12)
        width: Passed by the page slider. The graph fills the column.

    Returns:
        pyvis.network.Network: The generated family tree network
    """
    # Create the network. The canvas stays full width; rows come from levels.
    graph = net.Network(
        height=f"{height * 80}px",
        width="100%",
        bgcolor='white',
        font_color='black',
        directed=True,
        notebook=False
    )

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
      "edges": {
        "smooth": {
          "type": "cubicBezier",
          "forceDirection": "vertical",
          "roundness": 0.4
        }
      }
    }
    """)
    # Define node attributes
    def get_node_style(member: Dict[str, Any]) -> Dict[str, Any]:
        """Get node style based on member attributes."""
        style = {
            'color': {
                'background': '#ADD8E6',  # Light blue default
                'border': 'black'
            },
            'border_width': 1,
            'shape': 'box',
            'font': {
                'size': 32,
                'align': 'center',
                'color': 'black',
                'face': 'Arial',
                'bold': True
            }
        }
        
        # Highlight center member
        if member.get('id') == family_data.get('center', {}).get('id'):
            style.update({
                'color': {
                    'background': '#FFD700',  # Gold
                    'border': 'black'
                },
                'border_width': 3,
                'size': 30
            })
            
        # Style based on gender if available
        gender = member.get('sex', '').lower()
        if gender == 'f':
            style['color']['background'] = '#FFB6C1'  # Light pink
        elif gender == 'm':
            style['color']['background'] = '#ADD8E6'  # Light blue
            
        return style
    
    center = family_data.get('center') or {}
    center_level = generation_level(center, 0)

    # Add nodes to the graph
    def add_member_node(member: Dict[str, Any], fallback_level: int) -> None:
        """Add a member node on the row for that generation."""
        member_id = str(member['id'])
        
        # Create label with name and optional birth date
        name = member.get('name', 'Unknown')
        born = member.get('born', '')
        died = member.get('died', '')
        generation = member.get('gen_order', '0')
        
        label = f"{name}"
        if born:
            try:
                # Try parsing as YYYY-MM-DD first
                if '-' in born:
                    birth_year = datetime.strptime(born, '%Y-%m-%d').year
                else:  # Handle YYYY format
                    birth_year = int(born)
                label += f"\n*{birth_year}"
            except (ValueError, TypeError):
                # If parsing fails, just use the raw value
                if born and str(born).strip() not in ('', '0', '0000-00-00'):
                    label += f"\n*{born}"
                
        if died and str(died).strip() not in ('', '0', '0000-00-00'):
            try:
                # Try parsing as YYYY-MM-DD first
                if '-' in died:
                    death_year = datetime.strptime(died, '%Y-%m-%d').year
                else:  # Handle YYYY format
                    death_year = int(died)
                label += f"\n†{death_year}"
            except (ValueError, TypeError):
                # If parsing fails, just use the raw value
                label += f"\n†{died}"
        label += f"\n({generation})"
        
        # Add node with attributes
        graph.add_node(
            member_id,
            label=label,
            title=member_popup(member.get('id', 'N/A'), name),
            level=generation_level(member, fallback_level),
            **get_node_style(member)
        )
    
    # Add center member
    if 'center' in family_data and family_data['center']:
        add_member_node(family_data['center'], center_level)
    
    # Add parents
    parent_nodes = []
    for parent in family_data.get('parents', []):
        add_member_node(parent, center_level - 1)
        parent_nodes.append(str(parent['id']))
        
        # Connect to center
        if 'center' in family_data and family_data['center']:
            graph.add_edge(
                str(parent['id']), 
                str(family_data['center']['id']),
                color='#333333',
                width=1.5,
                arrows='to'
            )
    
    # Add children
    child_nodes = []
    for child in family_data.get('children', []):
        add_member_node(child, center_level + 1)
        child_nodes.append(str(child['id']))
        
        # Connect to center
        if 'center' in family_data and family_data['center']:
            graph.add_edge(
                str(family_data['center']['id']), 
                str(child['id']),
                color='#333333',
                width=1.5,
                arrows='to'
            )
    
    # Add grandparents
    grandparent_nodes = []
    for grandparent in family_data.get('grandparents', []):
        add_member_node(grandparent, center_level - 2)
        grandparent_nodes.append(str(grandparent['id']))
        
        # Connect to parents
        for parent in family_data.get('parents', []):
            parent_relations = dbm.get_member_relations(parent['id'])
            for rel in parent_relations:
                if rel['relation'] == 'parent' and rel['partner_id'] == grandparent['id']:
                    graph.add_edge(
                        str(grandparent['id']), 
                        str(parent['id']),
                        color='#333333',
                        width=1.5,
                        arrows='to'
                    )
    
    # Add grandchildren
    grandchild_nodes = []
    for grandchild in family_data.get('grandchildren', []):
        add_member_node(grandchild, center_level + 2)
        grandchild_nodes.append(str(grandchild['id']))
        
        # Connect to children
        for child in family_data.get('children', []):
            child_relations = dbm.get_member_relations(child['id'])
            for rel in child_relations:
                if rel['relation'] == 'child' and rel['partner_id'] == grandchild['id']:
                    graph.add_edge(
                        str(child['id']), 
                        str(grandchild['id']),
                        color='#333333',
                        width=1.5,
                        arrows='to'
                    )
    
    return spread_nodes_across_iframe(graph)

def main():
    """Main function to render the Streamlit app."""
    global UI_TEXTS
    
    render_sidebar()

    # Main content area --- from here
        
    st.header(f"{UI_TEXTS['family']} {UI_TEXTS['gen_order']} {UI_TEXTS['visualization']}")
    
    # Add a form for better user experience
    with st.form("family_tree_form"):
        st.subheader(f"{UI_TEXTS['search']} 3 {UI_TEXTS['gen_order']} {UI_TEXTS['up_and_down']}")

        # Get member ID from user input
        member_id = st.number_input(
            f"{UI_TEXTS['enter']} {UI_TEXTS['member']} {UI_TEXTS['id']}:",
            min_value=1,
            step=1,
            value=1,
            help=f"{UI_TEXTS['enter']} {UI_TEXTS['member']} {UI_TEXTS['id']}"
        )
        
        # Add graph configuration options
        col1, col2 = st.columns(2)
        with col1:
            graph_height = st.slider(
                f"{UI_TEXTS['graph_height']}:",
                min_value=1,
                max_value=30,
                value=12,
                step=1,
                help=f"{UI_TEXTS['adjust']} {UI_TEXTS['family_tree']} {UI_TEXTS['graph_height']}"
            )
        with col2:
            graph_width = st.slider(
                f"{UI_TEXTS['graph_width']}:",
                min_value=1,
                max_value=30,
                value=15,
                step=1,
                help=f"{UI_TEXTS['adjust']} {UI_TEXTS['family_tree']} {UI_TEXTS['graph_width']}"
            )
        
        submitted = st.form_submit_button(f"{UI_TEXTS['draw']} {UI_TEXTS['family_tree']}", type="primary")
    
    if submitted:
        if not member_id:
            st.warning(f"⚠️ {UI_TEXTS['member']} {UI_TEXTS['id']} {UI_TEXTS['required']}!")
            st.stop()
            
        # Create a container for the tree visualization
        tree_container = st.container()
        
        with st.spinner(f"{UI_TEXTS['draw']} {UI_TEXTS['family_tree']}..."):
            try:
                # Get family data with error handling
                family_data = get_family_members(member_id)
                
                if not family_data or 'center' not in family_data:
                    st.error(f"❌ {fu.get_function_name()} {UI_TEXTS['family']} {UI_TEXTS['not_found']}!")
                    st.stop()
                
                # Display the tree in the container
                with tree_container:
                    st.success(f"✅  {UI_TEXTS['draw']} {UI_TEXTS['family_tree']} {UI_TEXTS['successfully']}!")
                    
                    # Create and display the graph with user-specified settings
                    try:
                        graph = create_family_graph(
                            family_data,
                            height=graph_height,
                            width=graph_width,
                        )
                        
                        # Save the graph to HTML and display it.
                        # st.iframe always shows a scrollbar when the graph is taller than the frame.
                        graph_html = graph.generate_html()
                        st.iframe(
                            graph_html,
                            width="stretch",
                            height=graph_height * 80,
                            alt="Family tree",
                        )
                    except Exception as e:
                        fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['draw']} {UI_TEXTS['family_tree']} {UI_TEXTS['visualization']} {UI_TEXTS['failed']}", e)
                        logger.exception("Error in drawing family tree graph")
                    
                    # Display family information in an expandable section
                    center = family_data.get('center', {})
                    with st.expander(f"👨‍👩‍👧‍👦 {UI_TEXTS['search']} {UI_TEXTS['family']} {UI_TEXTS['details']}: {center.get('name', 'Unknown')} (ID: {center.get('id', 'N/A')})", expanded=True):
                        # Display family members in a structured way
                        cols = st.columns(3)
                        
                        with cols[0]:
                            if family_data.get('grandparents'):
                                st.markdown(f"### 👴👵 {UI_TEXTS['grandparents']}")
                                for gp in family_data['grandparents']:
                                    st.write(f"- {gp.get('name', 'Unknown')} (ID: {gp.get('id', 'N/A')})")
                                st.write("")
                            else:
                                st.info(f"{UI_TEXTS['grandparents']} {UI_TEXTS['not_found']}")
                        
                        with cols[1]:
                            if family_data.get('parents'):
                                st.markdown(f"### 👨‍👩‍👦 {UI_TEXTS['parents']}")
                                for p in family_data['parents']:
                                    st.write(f"- {p.get('name', 'Unknown')} (ID: {p.get('id', 'N/A')})")
                                st.write("")
                            else:
                                st.info(f"{UI_TEXTS['parents']} {UI_TEXTS['not_found']}")
                            
                            st.markdown(f"### 👤 {UI_TEXTS['center']} {UI_TEXTS['member']}")
                            st.write(f"- {center.get('name', 'Unknown')} (ID: {center.get('id', 'N/A')})")
                            
                            if family_data.get('children'):
                                st.markdown(f"### 👶 {UI_TEXTS['children']}")
                                for c in family_data['children']:
                                    st.write(f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')})")
                                st.write("")
                            else:
                                st.info(f"{UI_TEXTS['children']} {UI_TEXTS['not_found']}")
                        
                        with cols[2]:
                            if family_data.get('grandchildren'):
                                st.markdown(f"### 👶👶 {UI_TEXTS['grandchildren']}")
                                for gc in family_data['grandchildren']:
                                    st.write(f"- {gc.get('name', 'Unknown')} (ID: {gc.get('id', 'N/A')})")
                                st.write("")
                            else:
                                st.info(f"{UI_TEXTS['grandchildren']} {UI_TEXTS['not_found']}")
                
            except Exception as e:
                fu.show_user_error(f"❌ {fu.get_function_name()} {UI_TEXTS['draw']} {UI_TEXTS['family_tree']} {UI_TEXTS['visualization']} {UI_TEXTS['failed']}", e)
                logger.exception("Error in main")
                
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