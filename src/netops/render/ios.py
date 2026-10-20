"""IOS configuration renderer."""

from ipaddress import IPv4Network
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from netops.design.ipam import NetworkDesign

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def _network(prefix: str) -> str:
    return str(IPv4Network(prefix).network_address)


def _netmask(prefix: str) -> str:
    return str(IPv4Network(prefix).netmask)


def render_ios(design: NetworkDesign) -> str:
    """Render a stable IOS text configuration from a completed design."""
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    environment.filters["ipv4_network"] = _network
    environment.filters["ipv4_netmask"] = _netmask
    template = environment.get_template("ios.j2")
    return template.render(design=design).rstrip() + "\n"
