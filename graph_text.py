"""Text placed in graph pop-ups.

Pyvis renders a node's ``title`` as HTML. Member names are escaped so a
name cannot inject markup. The ``<br>`` separator is written by the
helper, not by the name.
"""
import html


def html_text(value):
    """Escape one value for an HTML pop-up."""
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def member_popup(member_id, name):
    """Pop-up for a person on the three-generation graph."""
    return f"ID: {html_text(member_id)}<br>Name: {html_text(name)}"


def center_popup(name):
    """Pop-up for the center person on the relationship graph."""
    return f"Center Member: {html_text(name)}"


def related_popup(name, relation):
    """Pop-up for a related person."""
    return f"Family Member: {html_text(name)}<br>Relation: {html_text(relation)}"


def relation_popup(relation):
    """Pop-up for an edge."""
    return f"Relation: {html_text(relation)}"
