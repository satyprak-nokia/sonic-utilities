import re
import click
# import subprocess
import utilities_common.cli as clicommon
from swsscommon.swsscommon import SonicV2Connector, ConfigDBConnector


##############################################################################
# 'spanning_tree' group ("show spanning_tree ...")
###############################################################################
#   STP show commands:-
#   show spanning_tree
#   show spanning_tree vlan <vlanid>
#   show spanning_tree vlan interface <vlanid> <ifname>
#   show spanning_tree bpdu_guard
#   show spanning_tree statistics
#   show spanning_tree statistics vlan <vlanid>
#   show spanning_tree mst
#   show spanning_tree mst <instance-id>
#   show spanning_tree mst <instance-id> detail
#   show spanning_tree mst configuration
#   show spanning_tree mst interface <interface_name>
#   show spanning_tree mst vlan <vlanid>
#
###############################################################################
g_stp_vlanid = 0
g_stp_mode = ''
g_stp_appl_db = None
g_stp_cfg_db = None
#
# Utility API's
#


def is_stp_docker_running():
    return True
#    running_docker = subprocess.check_output('docker ps', shell=True)
#    if running_docker.find("docker-stp".encode()) == -1:
#        return False
#    else:
#        return True


def connect_to_cfg_db():
    config_db = ConfigDBConnector()
    config_db.connect()
    return config_db


def connect_to_appl_db():
    appl_db = SonicV2Connector(host="127.0.0.1")
    appl_db.connect(appl_db.APPL_DB)
    return appl_db


# Redis DB only supports limiter pattern search wildcards.
# check https://redis.io/commands/KEYS before using this api
# Redis-db uses glob-style patterns not regex
def stp_get_key_from_pattern(db_connect, db, pattern):
    keys = db_connect.keys(db, pattern)
    if keys:
        return keys[0]
    else:
        return None


# get_all doesn't accept regex patterns, it requires exact key
def stp_get_all_from_pattern(db_connect, db, pattern):
    key = stp_get_key_from_pattern(db_connect, db, pattern)
    if key:
        entry = db_connect.get_all(db, key)
        return entry


def stp_is_port_fast_enabled(ifname):
    app_db_entry = stp_get_all_from_pattern(
        g_stp_appl_db, g_stp_appl_db.APPL_DB, "*STP_PORT_TABLE:{}".format(ifname))
    if (not app_db_entry or not ('port_fast' in app_db_entry) or app_db_entry['port_fast'] == 'no'):
        return False
    return True


def stp_is_uplink_fast_enabled(ifname):
    entry = g_stp_cfg_db.get_entry("STP_PORT", ifname)
    if (entry and ('uplink_fast' in entry) and entry['uplink_fast'] == 'true'):
        return True
    return False


def stp_get_entry_from_vlan_tb(db, vlanid):
    entry = stp_get_all_from_pattern(db, db.APPL_DB, "*STP_VLAN_TABLE:Vlan{}".format(vlanid))
    if not entry:
        return entry

    if 'bridge_id' not in entry:
        entry['bridge_id'] = 'NA'
    if 'max_age' not in entry:
        entry['max_age'] = '0'
    if 'hello_time' not in entry:
        entry['hello_time'] = '0'
    if 'forward_delay' not in entry:
        entry['forward_delay'] = '0'
    if 'hold_time' not in entry:
        entry['hold_time'] = '0'
    if 'last_topology_change' not in entry:
        entry['last_topology_change'] = '0'
    if 'topology_change_count' not in entry:
        entry['topology_change_count'] = '0'
    if 'root_bridge_id' not in entry:
        entry['root_bridge_id'] = 'NA'
    if 'root_path_cost' not in entry:
        entry['root_path_cost'] = '0'
    if 'desig_bridge_id' not in entry:
        entry['desig_bridge_id'] = 'NA'
    if 'root_port' not in entry:
        entry['root_port'] = 'NA'
    if 'root_max_age' not in entry:
        entry['root_max_age'] = '0'
    if 'root_hello_time' not in entry:
        entry['root_hello_time'] = '0'
    if 'root_forward_delay' not in entry:
        entry['root_forward_delay'] = '0'
    if 'stp_instance' not in entry:
        entry['stp_instance'] = '65535'

    return entry


def stp_get_entry_from_vlan_intf_tb(db, vlanid, ifname):
    entry = stp_get_all_from_pattern(db, db.APPL_DB, "*STP_VLAN_PORT_TABLE:Vlan{}:{}".format(vlanid, ifname))
    if not entry:
        return entry

    if 'port_num' not in entry:
        entry['port_num'] = 'NA'
    if 'priority' not in entry:
        entry['priority'] = '0'
    if 'path_cost' not in entry:
        entry['path_cost'] = '0'
    if 'root_guard' not in entry:
        entry['root_guard'] = 'NA'
    if 'bpdu_guard' not in entry:
        entry['bpdu_guard'] = 'NA'
    if 'port_state' not in entry:
        entry['port_state'] = 'NA'
    if 'desig_cost' not in entry:
        entry['desig_cost'] = '0'
    if 'desig_root' not in entry:
        entry['desig_root'] = 'NA'
    if 'desig_bridge' not in entry:
        entry['desig_bridge'] = 'NA'

    return entry


def stp_get_entry_from_mst_inst_tb(db, instance_id):
    entry = stp_get_all_from_pattern(
        db, db.APPL_DB, "*STP_MST_INST_TABLE:{}".format(instance_id))
    if not entry:
        return entry

    defaults = {
        'bridge_address': 'NA',
        'root_address': 'NA',
        'regional_root_address': 'NA',
        'root_path_cost': '0',
        'regional_root_cost': '0',
        'root_max_age': '0',
        'root_hello_time': '0',
        'root_forward_delay': '0',
        'hold_time': '0',
        'root_port': 'NA',
        'remaining_hops': '0',
        'bridge_priority': '0',
        'vlan@': '',
    }
    for field, default in defaults.items():
        if field not in entry:
            entry[field] = default

    return entry


def stp_get_entry_from_mst_port_tb(db, instance_id, ifname):
    entry = stp_get_all_from_pattern(
        db, db.APPL_DB, "*STP_MST_PORT_TABLE:{}:{}".format(instance_id, ifname))
    if not entry:
        return entry

    defaults = {
        'port_number': 'NA',
        'priority': '0',
        'path_cost': '0',
        'port_state': 'NA',
        'desig_cost': '0',
        'external_cost': '0',
        'desig_root': 'NA',
        'desig_reg_root': 'NA',
        'desig_bridge': 'NA',
        'role': 'NA',
        'rem_time': '0',
        'bpdu_sent': '-',
        'bpdu_received': '-',
    }
    for field, default in defaults.items():
        if field not in entry:
            entry[field] = default

    return entry


def stp_get_mst_instance_id_from_key(key):
    """Extract MST instance id from a ConfigDB STP_MST_INST key."""
    if isinstance(key, tuple):
        return int(key[-1])
    if isinstance(key, str) and '|' in key:
        return int(key.rsplit('|', 1)[-1])
    return int(key)


def stp_get_mst_instance_cfg_key(instance_id):
    """Build YANG-compatible CONFIG_DB key for STP_MST_INST (list key: instance)."""
    return str(instance_id)


def stp_get_mst_inst_cfg_entry(cfg_db, instance_id):
    """Read STP_MST_INST from CONFIG_DB (YANG key first, legacy key fallback)."""
    if not cfg_db:
        return {}

    for key in (stp_get_mst_instance_cfg_key(instance_id),
                'MST_INSTANCE|{}'.format(instance_id)):
        entry = cfg_db.get_entry('STP_MST_INST', key)
        if entry:
            return entry

    return {}


def stp_get_mst_instance_ids(db):
    keys = db.keys(db.APPL_DB, "*STP_MST_INST_TABLE:*")
    instance_ids = []
    if keys:
        for key in keys:
            result = re.search(r'STP_MST_INST_TABLE:(\d+)$', key)
            if result:
                instance_ids.append(int(result.group(1)))

    if not instance_ids and g_stp_cfg_db:
        cfg_keys = g_stp_cfg_db.get_keys("STP_MST_INST")
        for key in cfg_keys:
            try:
                instance_ids.append(stp_get_mst_instance_id_from_key(key))
            except (TypeError, ValueError):
                continue

    instance_ids = sorted(set(instance_ids))
    return instance_ids


def stp_get_mst_instance_for_vlan(cfg_db, vlanid):
    keys = cfg_db.get_keys("STP_MST_INST")
    if keys:
        for key in keys:
            entry = cfg_db.get_entry("STP_MST_INST", key)
            vlan_list = entry.get('vlan_list', '') if entry else ''
            if vlan_list and str(vlanid) in vlan_list.split(','):
                return stp_get_mst_instance_id_from_key(key)

    return 0


def stp_parse_vlan_id_from_key(key):
    """Extract numeric VLAN id from a ConfigDB VLAN key."""
    if isinstance(key, tuple):
        key = key[0] if key else ''
    if isinstance(key, str) and key.startswith('Vlan'):
        return int(key[4:])
    raise ValueError("invalid vlan key: {}".format(key))


def stp_get_configured_vlan_ids(cfg_db):
    vlan_ids = []
    keys = cfg_db.get_keys("VLAN")
    for key in keys:
        try:
            vlan_ids.append(stp_parse_vlan_id_from_key(key))
        except (TypeError, ValueError):
            continue
    vlan_ids.sort()
    return vlan_ids


def stp_get_mst_mapped_vlan_ids(cfg_db):
    mapped = set()
    keys = cfg_db.get_keys("STP_MST_INST")
    for key in keys:
        instance_id = stp_get_mst_instance_id_from_key(key)
        if instance_id == 0:
            continue
        entry = cfg_db.get_entry("STP_MST_INST", key)
        vlan_list = entry.get('vlan_list', '') if entry else ''
        if vlan_list:
            for vlan in vlan_list.split(','):
                vlan = vlan.strip()
                if vlan:
                    mapped.add(int(vlan))
    return mapped


def stp_format_vlan_id_list(vlan_ids):
    if not vlan_ids:
        return 'none'
    if len(vlan_ids) > 20:
        return "{} VLANs ({}-{})".format(len(vlan_ids), vlan_ids[0], vlan_ids[-1])
    return ','.join(str(vlan_id) for vlan_id in vlan_ids)


def stp_get_instance0_vlan_list(cfg_db):
    configured = stp_get_configured_vlan_ids(cfg_db)
    mapped = stp_get_mst_mapped_vlan_ids(cfg_db)
    unmapped = [vlan_id for vlan_id in configured if vlan_id not in mapped]
    return stp_format_vlan_id_list(unmapped)


def stp_get_vlan_list_for_mst_instance(cfg_db, instance_id):
    if instance_id == 0:
        return stp_get_instance0_vlan_list(cfg_db)

    entry = stp_get_mst_inst_cfg_entry(cfg_db, instance_id)
    if entry and entry.get('vlan_list'):
        return entry['vlan_list']

    return 'none'


def stp_format_mst_vlan_list(instance_id, inst_entry, cfg_vlan_list):
    """Format VLAN list for display; APPL_DB vlan@ is a full bitmap for instance 0."""
    if instance_id == 0:
        return cfg_vlan_list if cfg_vlan_list else 'none'

    if cfg_vlan_list and cfg_vlan_list not in ('none',):
        return cfg_vlan_list

    appl_vlans = inst_entry.get('vlan@', '')
    if not appl_vlans:
        return cfg_vlan_list if cfg_vlan_list else 'none'

    vlan_ids = [vlan.strip() for vlan in appl_vlans.split(',') if vlan.strip()]
    if len(vlan_ids) > 20:
        return "{} VLANs ({}-{})".format(len(vlan_ids), vlan_ids[0], vlan_ids[-1])

    return appl_vlans


def stp_get_stp_port_cfg_entry(ifname):
    if not g_stp_cfg_db:
        return {}
    entry = g_stp_cfg_db.get_entry("STP_PORT", ifname)
    return entry if entry else {}


def stp_get_port_edge_port_config(ifname):
    entry = stp_get_stp_port_cfg_entry(ifname)
    return 'Y' if entry.get('edge_port') == 'true' else 'N'


def stp_get_port_link_type(ifname):
    link_type = stp_get_stp_port_cfg_entry(ifname).get('link_type', '')
    return link_type if link_type else 'NA'


def stp_sort_interfaces(intf_list):
    eth_list = [ifname[len("Ethernet"):] for ifname in intf_list if ifname.startswith("Ethernet")]
    po_list = [ifname[len("PortChannel"):] for ifname in intf_list if ifname.startswith("PortChannel")]

    eth_list.sort()
    po_list.sort()

    sorted_list = []
    for port_num in eth_list:
        sorted_list.append("Ethernet" + str(port_num))
    for port_num in po_list:
        sorted_list.append("PortChannel" + port_num)

    return sorted_list


def stp_ensure_db_connected(silent=False):
    """Ensure STP DB handles are connected (needed for nested MST commands)."""
    global g_stp_appl_db
    global g_stp_cfg_db
    global g_stp_mode

    if not is_stp_docker_running():
        return False

    g_stp_appl_db = connect_to_appl_db()
    g_stp_cfg_db = connect_to_cfg_db()

    global_cfg = g_stp_cfg_db.get_entry("STP", "GLOBAL")
    if not global_cfg:
        if not silent:
            click.echo("Spanning-tree is not configured")
        return False

    if global_cfg.get('mode') == 'pvst':
        g_stp_mode = 'PVST'
    elif global_cfg.get('mode') == 'mst':
        g_stp_mode = 'MST'
    else:
        g_stp_mode = ''

    return True


def stp_ensure_mst_mode():
    if not stp_ensure_db_connected():
        return False

    global_cfg = g_stp_cfg_db.get_entry("STP", "GLOBAL")
    if global_cfg.get('mode') != 'mst':
        click.echo("Spanning-tree is not configured in MST mode")
        return False
    return True


def stp_print_mst_mode_header():
    global g_stp_mode
    if g_stp_mode:
        click.echo("Spanning-tree Mode: {}".format(g_stp_mode))
        g_stp_mode = ''


# Column widths for MST show output (dotted bridge IDs are 20 characters).
MST_BRIDGE_ID_W = 21
MST_ROOT_PATH_W = 12
MST_ROOT_PORT_W = 15
MST_TIME_W = 5
MST_PORT_NAME_W = 17
MST_PORT_PRIO_W = 6
MST_PORT_PATH_W = 10
MST_PORT_ROLE_W = 12
MST_PORT_EXT_COST_W = 10
MST_PORT_STATE_W = 14
MST_PORT_DESIG_COST_W = 12
MST_PORT_EDGE_W = 5
MST_PORT_LINK_TYPE_W = 14
MST_PORT_ROW_FMT = (
    "{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}")
MST_PORT_DETAIL_ROW_FMT = (
    "{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}")
MST_PORT_INTERFACE_ROW_FMT = (
    "{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}")

# YANG defaults for STP_MST|GLOBAL when fields are not explicitly configured.
MST_CFG_DEFAULT_REVISION = '0'
MST_CFG_DEFAULT_MAX_AGE = '20'
MST_CFG_DEFAULT_HELLO_TIME = '2'
MST_CFG_DEFAULT_FORWARD_DELAY = '15'
MST_CFG_DEFAULT_MAX_HOPS = '20'


def stp_print_mst_port_interface_header():
    click.echo(MST_PORT_INTERFACE_ROW_FMT.format(
        "Port", MST_PORT_NAME_W,
        "Prio", MST_PORT_PRIO_W,
        "Path", MST_PORT_PATH_W,
        "Edge", MST_PORT_EDGE_W,
        "Link", MST_PORT_LINK_TYPE_W,
        "Role", MST_PORT_ROLE_W,
        "External", MST_PORT_EXT_COST_W,
        "State", MST_PORT_STATE_W,
        "Designated", MST_PORT_DESIG_COST_W,
        "Designated", MST_BRIDGE_ID_W,
        "Designated", MST_BRIDGE_ID_W))
    click.echo(MST_PORT_INTERFACE_ROW_FMT.format(
        "Name", MST_PORT_NAME_W,
        "rity", MST_PORT_PRIO_W,
        "Cost", MST_PORT_PATH_W,
        "Port", MST_PORT_EDGE_W,
        "Type", MST_PORT_LINK_TYPE_W,
        "", MST_PORT_ROLE_W,
        "Cost", MST_PORT_EXT_COST_W,
        "", MST_PORT_STATE_W,
        "Cost", MST_PORT_DESIG_COST_W,
        "Root", MST_BRIDGE_ID_W,
        "Bridge", MST_BRIDGE_ID_W))


def stp_print_mst_port_detail_header():
    click.echo(MST_PORT_DETAIL_ROW_FMT.format(
        "Port", MST_PORT_NAME_W,
        "Prio", MST_PORT_PRIO_W,
        "Path", MST_PORT_PATH_W,
        "Role", MST_PORT_ROLE_W,
        "External", MST_PORT_EXT_COST_W,
        "State", MST_PORT_STATE_W,
        "Designated", MST_PORT_DESIG_COST_W,
        "Designated", MST_BRIDGE_ID_W,
        "Designated", MST_BRIDGE_ID_W))
    click.echo(MST_PORT_DETAIL_ROW_FMT.format(
        "Name", MST_PORT_NAME_W,
        "rity", MST_PORT_PRIO_W,
        "Cost", MST_PORT_PATH_W,
        "", MST_PORT_ROLE_W,
        "Cost", MST_PORT_EXT_COST_W,
        "", MST_PORT_STATE_W,
        "Cost", MST_PORT_DESIG_COST_W,
        "Root", MST_BRIDGE_ID_W,
        "Bridge", MST_BRIDGE_ID_W))


def stp_print_mst_port_summary_header():
    click.echo(MST_PORT_ROW_FMT.format(
        "Port", MST_PORT_NAME_W,
        "Prio", MST_PORT_PRIO_W,
        "Path", MST_PORT_PATH_W,
        "Role", MST_PORT_ROLE_W,
        "State", MST_PORT_STATE_W,
        "Designated", MST_PORT_DESIG_COST_W,
        "Designated", MST_BRIDGE_ID_W,
        "Designated", MST_BRIDGE_ID_W))
    click.echo(MST_PORT_ROW_FMT.format(
        "Name", MST_PORT_NAME_W,
        "rity", MST_PORT_PRIO_W,
        "Cost", MST_PORT_PATH_W,
        "", MST_PORT_ROLE_W,
        "", MST_PORT_STATE_W,
        "Cost", MST_PORT_DESIG_COST_W,
        "Root", MST_BRIDGE_ID_W,
        "Bridge", MST_BRIDGE_ID_W))


def stp_display_mst_port(instance_id, ifname, detail=False, show_config=False):
    port_entry = stp_get_entry_from_mst_port_tb(g_stp_appl_db, instance_id, ifname)
    if not port_entry:
        return

    if show_config:
        click.echo(MST_PORT_INTERFACE_ROW_FMT.format(
            ifname, MST_PORT_NAME_W,
            port_entry['priority'], MST_PORT_PRIO_W,
            port_entry['path_cost'], MST_PORT_PATH_W,
            stp_get_port_edge_port_config(ifname), MST_PORT_EDGE_W,
            stp_get_port_link_type(ifname), MST_PORT_LINK_TYPE_W,
            port_entry['role'], MST_PORT_ROLE_W,
            port_entry['external_cost'], MST_PORT_EXT_COST_W,
            port_entry['port_state'], MST_PORT_STATE_W,
            port_entry['desig_cost'], MST_PORT_DESIG_COST_W,
            port_entry['desig_root'], MST_BRIDGE_ID_W,
            port_entry['desig_bridge'], MST_BRIDGE_ID_W))
        return

    if detail:
        click.echo(MST_PORT_DETAIL_ROW_FMT.format(
            ifname, MST_PORT_NAME_W,
            port_entry['priority'], MST_PORT_PRIO_W,
            port_entry['path_cost'], MST_PORT_PATH_W,
            port_entry['role'], MST_PORT_ROLE_W,
            port_entry['external_cost'], MST_PORT_EXT_COST_W,
            port_entry['port_state'], MST_PORT_STATE_W,
            port_entry['desig_cost'], MST_PORT_DESIG_COST_W,
            port_entry['desig_root'], MST_BRIDGE_ID_W,
            port_entry['desig_bridge'], MST_BRIDGE_ID_W))
    else:
        click.echo(MST_PORT_ROW_FMT.format(
            ifname, MST_PORT_NAME_W,
            port_entry['priority'], MST_PORT_PRIO_W,
            port_entry['path_cost'], MST_PORT_PATH_W,
            port_entry['role'], MST_PORT_ROLE_W,
            port_entry['port_state'], MST_PORT_STATE_W,
            port_entry['desig_cost'], MST_PORT_DESIG_COST_W,
            port_entry['desig_root'], MST_BRIDGE_ID_W,
            port_entry['desig_bridge'], MST_BRIDGE_ID_W))


def stp_display_mst_instance(instance_id, detail=False):
    inst_entry = stp_get_entry_from_mst_inst_tb(g_stp_appl_db, instance_id)
    if not inst_entry:
        return

    stp_print_mst_mode_header()
    cfg_vlan_list = stp_get_vlan_list_for_mst_instance(g_stp_cfg_db, instance_id)
    vlan_list = stp_format_mst_vlan_list(instance_id, inst_entry, cfg_vlan_list)

    click.echo("")
    click.echo("MST Instance {} - VLANs: {}".format(instance_id, vlan_list))
    click.echo("--------------------------------------------------------------------")
    click.echo("MST Bridge Parameters:")

    click.echo("{:21}{:10}{:7}{:7}{:7}{:6}".format(
        "Bridge", "Bridge", "Root", "Root", "Root", "Hold"))
    click.echo("{:21}{:10}{:7}{:7}{:7}{:6}".format(
        "Identifier", "Priority", "MaxAge", "Hello", "FwdDly", "Time"))
    click.echo("{:21}{:10}{:7}{:7}{:7}{:6}".format(
        "hex", "", "sec", "sec", "sec", "sec"))
    click.echo("{:21}{:10}{:7}{:7}{:7}{:6}".format(
        inst_entry['bridge_address'],
        inst_entry['bridge_priority'],
        inst_entry['root_max_age'],
        inst_entry['root_hello_time'],
        inst_entry['root_forward_delay'],
        inst_entry['hold_time']))

    click.echo("")
    click.echo("{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{}".format(
        "RootBridge", MST_BRIDGE_ID_W,
        "RootPath", MST_ROOT_PATH_W,
        "RegionalRoot", MST_BRIDGE_ID_W,
        "RootPort", MST_ROOT_PORT_W,
        "Max", MST_TIME_W,
        "Hel", MST_TIME_W,
        "Fwd", MST_TIME_W))
    click.echo("{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{}".format(
        "Identifier", MST_BRIDGE_ID_W,
        "Cost", MST_ROOT_PATH_W,
        "Identifier", MST_BRIDGE_ID_W,
        "", MST_ROOT_PORT_W,
        "Age", MST_TIME_W,
        "lo", MST_TIME_W,
        "Dly", MST_TIME_W))
    click.echo("{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{}".format(
        "hex", MST_BRIDGE_ID_W,
        "", MST_ROOT_PATH_W,
        "hex", MST_BRIDGE_ID_W,
        "", MST_ROOT_PORT_W,
        "sec", MST_TIME_W,
        "sec", MST_TIME_W,
        "sec", MST_TIME_W))
    click.echo("{:{}}{:{}}{:{}}{:{}}{:{}}{:{}}{}".format(
        inst_entry['root_address'], MST_BRIDGE_ID_W,
        inst_entry['root_path_cost'], MST_ROOT_PATH_W,
        inst_entry['regional_root_address'], MST_BRIDGE_ID_W,
        inst_entry['root_port'], MST_ROOT_PORT_W,
        inst_entry['root_max_age'], MST_TIME_W,
        inst_entry['root_hello_time'], MST_TIME_W,
        inst_entry['root_forward_delay'], MST_TIME_W))

    if detail:
        click.echo("")
        click.echo("Regional Root Cost: {}  Remaining Hops: {}".format(
            inst_entry['regional_root_cost'], inst_entry['remaining_hops']))

    click.echo("")
    click.echo("MST Port Parameters:")
    if detail:
        stp_print_mst_port_detail_header()
    else:
        stp_print_mst_port_summary_header()

    keys = g_stp_appl_db.keys(
        g_stp_appl_db.APPL_DB, "*STP_MST_PORT_TABLE:{}:*".format(instance_id))
    if not keys:
        return

    intf_list = []
    for key in keys:
        result = re.search(r'STP_MST_PORT_TABLE:\d+:(.*)$', key)
        if result:
            intf_list.append(result.group(1))

    for ifname in stp_sort_interfaces(intf_list):
        stp_display_mst_port(instance_id, ifname, detail=detail)


def stp_display_mst_configuration():
    mst_global = g_stp_cfg_db.get_entry("STP_MST", "GLOBAL")
    inst_keys = g_stp_cfg_db.get_keys("STP_MST_INST")

    if not mst_global and not inst_keys:
        click.echo("MST configuration is not available")
        return

    if mst_global is None:
        mst_global = {}

    click.echo("MST Global Configuration")
    click.echo("--------------------------------------------------------------------")
    click.echo("Region Name     : {}".format(mst_global.get('name', '')))
    click.echo("Revision        : {}".format(
        mst_global.get('revision', MST_CFG_DEFAULT_REVISION)))
    click.echo("Max Age         : {} sec".format(
        mst_global.get('max_age', MST_CFG_DEFAULT_MAX_AGE)))
    click.echo("Hello Time      : {} sec".format(
        mst_global.get('hello_time', MST_CFG_DEFAULT_HELLO_TIME)))
    click.echo("Forward Delay   : {} sec".format(
        mst_global.get('forward_delay', MST_CFG_DEFAULT_FORWARD_DELAY)))
    click.echo("Max Hops        : {}".format(
        mst_global.get('max_hops', MST_CFG_DEFAULT_MAX_HOPS)))
    click.echo("")

    if not inst_keys:
        return

    click.echo("MST Instance Configuration")
    click.echo("--------------------------------------------------------------------")
    click.echo("{:12}{:18}{}".format("Instance", "Bridge Priority", "VLAN List"))
    for key in sorted(inst_keys, key=stp_get_mst_instance_id_from_key):
        instance_id = stp_get_mst_instance_id_from_key(key)
        entry = g_stp_cfg_db.get_entry("STP_MST_INST", key)
        vlan_list = entry.get('vlan_list', '') if entry else ''
        if str(instance_id) == '0' and not vlan_list:
            vlan_list = stp_get_instance0_vlan_list(g_stp_cfg_db)
        click.echo("{:12}{:18}{}".format(
            str(instance_id),
            entry.get('bridge_priority', 'NA') if entry else 'NA',
            vlan_list if vlan_list else 'none'))


class MstInstanceShowGroup(click.Group):
    """Dynamic group for 'show spanning-tree mst <instance-id> [detail]'."""

    def __init__(self, instance_id, **attrs):
        super().__init__(invoke_without_command=True, **attrs)
        self.instance_id = instance_id
        self.name = str(instance_id)

    def invoke(self, ctx):
        # Click passes 'detail' via protected_args for dynamically resolved groups.
        detail = (
            ctx.invoked_subcommand == 'detail' or
            (ctx.protected_args and ctx.protected_args[0] == 'detail')
        )
        if not stp_ensure_mst_mode():
            return
        stp_display_mst_instance(self.instance_id, detail=detail)


class StpMstGroup(clicommon.AliasedGroup):
    """MST show group that accepts numeric instance IDs as subcommands."""

    def get_command(self, ctx, cmd_name):
        rv = super().get_command(ctx, cmd_name)
        if rv is not None:
            return rv
        if cmd_name.isdigit():
            return MstInstanceShowGroup(instance_id=int(cmd_name))
        return None


#
# This group houses Spanning_tree commands and subgroups
@click.group(cls=clicommon.AliasedGroup, invoke_without_command=True)
@click.pass_context
def spanning_tree(ctx):
    """Show spanning_tree commands"""
    if not is_stp_docker_running():
        ctx.fail("STP docker is not running")

    if not stp_ensure_db_connected(silent=(ctx.invoked_subcommand is not None)):
        return

    global_cfg = g_stp_cfg_db.get_entry("STP", "GLOBAL")

    if ctx.invoked_subcommand is None:
        if global_cfg.get('mode') == 'mst':
            instance_ids = stp_get_mst_instance_ids(g_stp_appl_db)
            if not instance_ids:
                click.echo("No MST instance information available")
                return
            for instance_id in instance_ids:
                stp_display_mst_instance(instance_id)
            return

        keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_VLAN_TABLE:Vlan*")
        if not keys:
            return
        vlan_list = []
        for key in keys:
            result = re.search('.STP_VLAN_TABLE:Vlan(.*)', key)
            vlanid = result.group(1)
            vlan_list.append(int(vlanid))
        vlan_list.sort()
        for vlanid in vlan_list:
            ctx.invoke(show_stp_vlan, vlanid=vlanid)


@spanning_tree.group('vlan', cls=clicommon.AliasedGroup, invoke_without_command=True)
@click.argument('vlanid', metavar='<vlanid>', required=True, type=int)
@click.pass_context
def show_stp_vlan(ctx, vlanid):
    """Show spanning_tree vlan <vlanid> information"""
    global g_stp_vlanid
    g_stp_vlanid = vlanid

    vlan_tb_entry = stp_get_entry_from_vlan_tb(g_stp_appl_db, g_stp_vlanid)
    if not vlan_tb_entry:
        return

    global g_stp_mode
    if g_stp_mode:
        click.echo("Spanning-tree Mode: {}".format(g_stp_mode))
        # reset so we dont print again
        g_stp_mode = ''

    click.echo("")
    click.echo("VLAN {} - STP instance {}".format(g_stp_vlanid, vlan_tb_entry['stp_instance']))
    click.echo("--------------------------------------------------------------------")
    click.echo("STP Bridge Parameters:")

    click.echo("{:17}{:7}{:7}{:7}{:6}{:13}{}".format(
        "Bridge", "Bridge", "Bridge", "Bridge", "Hold", "LastTopology", "Topology"))
    click.echo("{:17}{:7}{:7}{:7}{:6}{:13}{}".format(
        "Identifier", "MaxAge", "Hello", "FwdDly", "Time", "Change", "Change"))
    click.echo("{:17}{:7}{:7}{:7}{:6}{:13}{}".format("hex", "sec", "sec", "sec", "sec", "sec", "cnt"))
    click.echo("{:17}{:7}{:7}{:7}{:6}{:13}{}".format(
               vlan_tb_entry['bridge_id'],
               vlan_tb_entry['max_age'],
               vlan_tb_entry['hello_time'],
               vlan_tb_entry['forward_delay'],
               vlan_tb_entry['hold_time'],
               vlan_tb_entry['last_topology_change'],
               vlan_tb_entry['topology_change_count']))

    click.echo("")
    click.echo("{:17}{:10}{:18}{:19}{:4}{:4}{}".format(
        "RootBridge", "RootPath", "DesignatedBridge", "RootPort", "Max", "Hel", "Fwd"))
    click.echo("{:17}{:10}{:18}{:19}{:4}{:4}{}".format("Identifier", "Cost", "Identifier", "", "Age", "lo", "Dly"))
    click.echo("{:17}{:10}{:18}{:19}{:4}{:4}{}".format("hex", "", "hex", "", "sec", "sec", "sec"))
    click.echo("{:17}{:10}{:18}{:19}{:4}{:4}{}".format(
               vlan_tb_entry['root_bridge_id'],
               vlan_tb_entry['root_path_cost'],
               vlan_tb_entry['desig_bridge_id'],
               vlan_tb_entry['root_port'],
               vlan_tb_entry['root_max_age'],
               vlan_tb_entry['root_hello_time'],
               vlan_tb_entry['root_forward_delay']))

    click.echo("")
    click.echo("STP Port Parameters:")
    click.echo("{:17}{:5}{:10}{:5}{:7}{:14}{:12}{:17}{}".format(
        "Port", "Prio", "Path", "Port", "Uplink", "State", "Designated", "Designated", "Designated"))
    click.echo("{:17}{:5}{:10}{:5}{:7}{:14}{:12}{:17}{}".format(
        "Name", "rity", "Cost", "Fast", "Fast", "", "Cost", "Root", "Bridge"))
    if ctx.invoked_subcommand is None:
        keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_VLAN_PORT_TABLE:Vlan{}:*".format(vlanid))
        if not keys:
            return
        intf_list = []
        for key in keys:
            result = re.search('.STP_VLAN_PORT_TABLE:Vlan{}:(.*)'.format(vlanid), key)
            ifname = result.group(1)
            intf_list.append(ifname)
        eth_list = [ifname[len("Ethernet"):] for ifname in intf_list if ifname.startswith("Ethernet")]
        po_list = [ifname[len("PortChannel"):] for ifname in intf_list if ifname.startswith("PortChannel")]

        eth_list.sort()
        po_list.sort()
        for port_num in eth_list:
            ctx.invoke(show_stp_interface, ifname="Ethernet"+str(port_num))
        for port_num in po_list:
            ctx.invoke(show_stp_interface, ifname="PortChannel"+port_num)


@show_stp_vlan.command('interface')
@click.argument('ifname', metavar='<interface_name>', required=True)
@click.pass_context
def show_stp_interface(ctx, ifname):
    """Show spanning_tree vlan interface <vlanid> <ifname> information"""

    vlan_intf_tb_entry = stp_get_entry_from_vlan_intf_tb(g_stp_appl_db, g_stp_vlanid, ifname)
    if not vlan_intf_tb_entry:
        return

    click.echo("{:17}{:5}{:10}{:5}{:7}{:14}{:12}{:17}{}".format(
        ifname,
        vlan_intf_tb_entry['priority'],
        vlan_intf_tb_entry['path_cost'],
        'Y' if (stp_is_port_fast_enabled(ifname)) else 'N',
        'Y' if (stp_is_uplink_fast_enabled(ifname)) else 'N',
        vlan_intf_tb_entry['port_state'],
        vlan_intf_tb_entry['desig_cost'],
        vlan_intf_tb_entry['desig_root'],
        vlan_intf_tb_entry['desig_bridge']
        ))


@spanning_tree.command('bpdu_guard')
@click.pass_context
def show_stp_bpdu_guard(ctx):
    """Show spanning_tree bpdu_guard"""

    print_header = 1
    ifname_all = g_stp_cfg_db.get_keys("STP_PORT")
    for ifname in ifname_all:
        cfg_entry = g_stp_cfg_db.get_entry("STP_PORT", ifname)
        if cfg_entry['bpdu_guard'] == 'true' and cfg_entry['enabled'] == 'true':
            if print_header:
                click.echo("{:17}{:13}{}".format("PortNum", "Shutdown", "Port Shut"))
                click.echo("{:17}{:13}{}".format("", "Configured", "due to BPDU guard"))
                click.echo("-------------------------------------------")
                print_header = 0

            if cfg_entry['bpdu_guard_do_disable'] == 'true':
                disabled = 'No'
                keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_PORT_TABLE:{}".format(ifname))
                # only 1 key per ifname is expected in BPDU_GUARD_TABLE.
                if keys:
                    appdb_entry = g_stp_appl_db.get_all(g_stp_appl_db.APPL_DB, keys[0])
                    if appdb_entry and 'bpdu_guard_shutdown' in appdb_entry:
                        if appdb_entry['bpdu_guard_shutdown'] == 'yes':
                            disabled = 'Yes'
                click.echo("{:17}{:13}{}".format(ifname, "Yes", disabled))
            else:
                click.echo("{:17}{:13}{}".format(ifname, "No", "NA"))


@spanning_tree.command('root_guard')
@click.pass_context
def show_stp_root_guard(ctx):
    """Show spanning_tree root_guard"""

    print_header = 1
    ifname_all = g_stp_cfg_db.get_keys("STP_PORT")
    for ifname in ifname_all:
        entry = g_stp_cfg_db.get_entry("STP_PORT", ifname)
        if entry['root_guard'] == 'true' and entry['enabled'] == 'true':
            if print_header:
                global_entry = g_stp_cfg_db.get_entry("STP", "GLOBAL")
                click.echo("Root guard timeout: {} secs".format(global_entry['rootguard_timeout']))
                click.echo("")
                click.echo("{:17}{:7}{}".format("Port", "VLAN", "Current State"))
                click.echo("-------------------------------------------")
                print_header = 0

            state = ''
            vlanid = ''
            keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_VLAN_PORT_TABLE:*:{}".format(ifname))
            if keys:
                for key in keys:
                    entry = g_stp_appl_db.get_all(g_stp_appl_db.APPL_DB, key)
                    if entry and 'root_guard_timer' in entry:
                        if entry['root_guard_timer'] == '0':
                            state = 'Consistent state'
                        else:
                            state = 'Inconsistent state ({} seconds left on timer)'.format(entry['root_guard_timer'])

                        vlanid = re.search(':Vlan(.*):', key)
                        if vlanid:
                            click.echo("{:17}{:7}{}".format(ifname, vlanid.group(1), state))
                        else:
                            click.echo("{:17}{:7}{}".format(ifname, vlanid, state))


@spanning_tree.group('statistics', cls=clicommon.AliasedGroup, invoke_without_command=True)
@click.pass_context
def show_stp_statistics(ctx):
    """Show spanning_tree statistics"""

    if ctx.invoked_subcommand is None:
        keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_VLAN_TABLE:Vlan*")
        if not keys:
            return

        vlan_list = []
        for key in keys:
            result = re.search('.STP_VLAN_TABLE:Vlan(.*)', key)
            vlanid = result.group(1)
            vlan_list.append(int(vlanid))
        vlan_list.sort()
        for vlanid in vlan_list:
            ctx.invoke(show_stp_vlan_statistics, vlanid=vlanid)


@show_stp_statistics.command('vlan')
@click.argument('vlanid', metavar='<vlanid>', required=True, type=int)
@click.pass_context
def show_stp_vlan_statistics(ctx, vlanid):
    """Show spanning_tree statistics vlan"""

    stp_inst_entry = stp_get_all_from_pattern(
        g_stp_appl_db, g_stp_appl_db.APPL_DB, "*STP_VLAN_TABLE:Vlan{}".format(vlanid))
    if not stp_inst_entry:
        return

    click.echo("VLAN {} - STP instance {}".format(vlanid, stp_inst_entry['stp_instance']))
    click.echo("--------------------------------------------------------------------")
    click.echo("{:17}{:15}{:15}{:15}{}".format("PortNum", "BPDU Tx", "BPDU Rx", "TCN Tx", "TCN Rx"))
    keys = g_stp_appl_db.keys(g_stp_appl_db.APPL_DB, "*STP_VLAN_PORT_TABLE:Vlan{}:*".format(vlanid))
    if keys:
        for key in keys:
            result = re.search('.STP_VLAN_PORT_TABLE:Vlan(.*):(.*)', key)
            ifname = result.group(2)
            entry = g_stp_appl_db.get_all(g_stp_appl_db.APPL_DB, key)
            if entry:
                if 'bpdu_sent' not in entry:
                    entry['bpdu_sent'] = '-'
                if 'bpdu_received' not in entry:
                    entry['bpdu_received'] = '-'
                if 'tc_sent' not in entry:
                    entry['tc_sent'] = '-'
                if 'tc_received' not in entry:
                    entry['tc_received'] = '-'

                click.echo("{:17}{:15}{:15}{:15}{}".format(
                    ifname, entry['bpdu_sent'], entry['bpdu_received'], entry['tc_sent'], entry['tc_received']))


@spanning_tree.group('mst', cls=StpMstGroup, invoke_without_command=True)
@click.pass_context
def show_stp_mst(ctx):
    """Show spanning_tree MST information"""
    if ctx.invoked_subcommand is None:
        if not stp_ensure_mst_mode():
            return

        instance_ids = stp_get_mst_instance_ids(g_stp_appl_db)
        if not instance_ids:
            click.echo("No MST instance information available")
            return

        for instance_id in instance_ids:
            stp_display_mst_instance(instance_id)


@show_stp_mst.command('configuration')
@click.pass_context
def show_stp_mst_configuration(ctx):
    """Show spanning_tree MST configuration"""
    if not stp_ensure_mst_mode():
        return

    stp_display_mst_configuration()


@show_stp_mst.command('interface')
@click.argument('ifname_parts', metavar='<interface_name>', nargs=-1, required=True)
@click.pass_context
def show_stp_mst_interface(ctx, ifname_parts):
    """Show spanning_tree MST interface information"""
    if not stp_ensure_mst_mode():
        return

    if len(ifname_parts) == 1:
        ifname = ifname_parts[0]
    elif len(ifname_parts) == 2:
        ifname = ifname_parts[0] + ifname_parts[1]
    else:
        ctx.fail("Invalid interface name")

    instance_ids = stp_get_mst_instance_ids(g_stp_appl_db)
    if not instance_ids:
        click.echo("No MST instance information available")
        return

    found = False
    for instance_id in instance_ids:
        port_entry = stp_get_entry_from_mst_port_tb(g_stp_appl_db, instance_id, ifname)
        if not port_entry:
            continue

        found = True
        stp_print_mst_mode_header()
        click.echo("")
        click.echo("MST Instance {} - Interface {}".format(instance_id, ifname))
        click.echo("--------------------------------------------------------------------")
        stp_print_mst_port_interface_header()
        stp_display_mst_port(instance_id, ifname, detail=True, show_config=True)

    if not found:
        click.echo("No MST information for interface {}".format(ifname))


@show_stp_mst.command('vlan')
@click.argument('vlanid', metavar='<vlanid>', required=True, type=int)
@click.pass_context
def show_stp_mst_vlan(ctx, vlanid):
    """Show spanning_tree MST information for VLAN mapped instance"""
    if not stp_ensure_mst_mode():
        return

    instance_id = stp_get_mst_instance_for_vlan(g_stp_cfg_db, vlanid)
    stp_display_mst_instance(instance_id)
