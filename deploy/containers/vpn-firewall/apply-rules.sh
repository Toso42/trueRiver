#!/bin/sh
set -eu

WG_INTERFACE="${TRIVER_VPN_INTERFACE:-wg0}"
PROXY_IP="${TRIVER_PROXY_VPN_IP:-10.44.0.2}"
PROXY_PORTS="${TRIVER_PROXY_ALLOWED_PORTS:-80}"
CHECK_INTERVAL="${TRIVER_VPN_FIREWALL_CHECK_INTERVAL:-2}"

echo "Waiting for WireGuard interface ${WG_INTERFACE}..."
while ! ip link show "${WG_INTERFACE}" >/dev/null 2>&1; do
  sleep "${CHECK_INTERVAL}"
done

echo "Applying trueRiver VPN firewall rules for proxy ${PROXY_IP}..."
iptables -w -N TRIVER_VPN_ONLY 2>/dev/null || true
iptables -w -F TRIVER_VPN_ONLY
iptables -w -A TRIVER_VPN_ONLY -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

for port in ${PROXY_PORTS}; do
  iptables -w -A TRIVER_VPN_ONLY -i "${WG_INTERFACE}" -d "${PROXY_IP}" -p tcp --dport "${port}" -j ACCEPT
done

iptables -w -A TRIVER_VPN_ONLY -i "${WG_INTERFACE}" -j REJECT
iptables -w -C FORWARD -j TRIVER_VPN_ONLY 2>/dev/null || iptables -w -I FORWARD 1 -j TRIVER_VPN_ONLY

echo "trueRiver VPN firewall active."
tail -f /dev/null
