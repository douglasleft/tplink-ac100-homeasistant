"""Constants for TP-Link TL-AC100 integration."""

DOMAIN = "tplink_ac100"

CONF_HOST = "host"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_CONSIDER_HOME = "consider_home"

DEFAULT_SCAN_INTERVAL = 30
DEFAULT_CONSIDER_HOME = 180
DEFAULT_USERNAME = "admin"

API_TIMEOUT = 10

AUTH_TYPE_MAP = {
    "no_auth": "No Auth",
    "web": "Web",
    "wechat": "WeChat",
    "onekey": "One-Key",
    "sms": "SMS",
    "remote": "Remote",
    "cmcc": "CMCC",
    "wechatv2": "WeChat v2",
    "cloud": "Cloud",
    "mac": "MAC",
    "qrcode": "QR Code",
}
