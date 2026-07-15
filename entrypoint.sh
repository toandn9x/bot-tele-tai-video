#!/bin/sh
# Khởi động Cloudflare WARP ở chế độ proxy (SOCKS5 127.0.0.1:40000) rồi chạy bot.
# YouTube chặn IP datacenter; đi qua WARP thì YouTube thấy IP Cloudflare (ít bị chặn).
# Tắt bằng biến môi trường USE_WARP=0. Nếu WARP không kết nối được thì bot vẫn
# chạy bình thường (chỉ YouTube có thể bị chặn), không làm hỏng nền tảng khác.

if [ "${USE_WARP:-1}" = "1" ]; then
  echo "[warp] khởi động daemon..."
  mkdir -p /var/lib/cloudflare-warp
  warp-svc >/tmp/warp-svc.log 2>&1 &

  # đợi daemon sẵn sàng
  i=0
  while [ $i -lt 15 ]; do
    if warp-cli --accept-tos status >/dev/null 2>&1; then break; fi
    i=$((i + 1)); sleep 1
  done

  warp-cli --accept-tos registration new >/dev/null 2>&1 || echo "[warp] đăng ký lỗi/bỏ qua"
  warp-cli --accept-tos mode proxy      >/dev/null 2>&1 || echo "[warp] đặt proxy mode lỗi"
  warp-cli --accept-tos connect         >/dev/null 2>&1 || echo "[warp] connect lỗi"

  # đợi tới khi Connected (tối đa ~20s)
  i=0
  while [ $i -lt 20 ]; do
    if warp-cli --accept-tos status 2>/dev/null | grep -qi "Connected"; then
      echo "[warp] đã kết nối — YouTube sẽ đi qua WARP"
      export PROXY_URL="socks5://127.0.0.1:40000"
      break
    fi
    i=$((i + 1)); sleep 1
  done

  if [ -z "$PROXY_URL" ]; then
    echo "[warp] KHÔNG kết nối được — chạy không proxy (YouTube có thể vẫn bị chặn)"
    cat /tmp/warp-svc.log 2>/dev/null | tail -5
  fi
fi

exec python bot.py
