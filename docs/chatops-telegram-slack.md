# Chatops — Telegram & Slack (Phase A, 2026-08-31)

Cả hai kênh chat đều **chỉ-đọc + phê duyệt**: hỏi trạng thái hệ thống và
bấm nút duyệt/từ chối action. Không có đường nào từ chat ra lệnh thay đổi —
Phase B (lệnh thay đổi từ chat) bị chặn cho tới khi có bảng map chat-user →
local-user (fail-closed).

## Telegram

### Setup

1. Tạo bot với @BotFather → lấy `TELEGRAM_BOT_TOKEN`.
2. Đặt `TELEGRAM_WEBHOOK_SECRET` (chuỗi ngẫu nhiên tự chọn, vd
   `python -c 'import secrets; print(secrets.token_hex(32))'`).
3. Đăng ký webhook (Telegram sẽ gửi lại secret trong header
   `X-Telegram-Bot-Api-Secret-Token` ở mỗi update):

   ```
   https://api.telegram.org/bot<TOKEN>/setWebhook
     ?url=https://<host>/api/v1/approvals/webhook/telegram
     &secret_token=<TELEGRAM_WEBHOOK_SECRET>
   ```

4. Lấy chat id của nhóm/cá nhân cần cấp quyền (nhắn bot rồi mở
   `getUpdates`), điền vào `TELEGRAM_ALLOWED_CHAT_IDS` — **danh sách rỗng
   = chặn mọi chat** (fail-closed).

### Lệnh

| Lệnh | Kết quả |
|------|---------|
| `/status` | Snapshot sức khỏe 4 hệ thống + số alert firing (dùng đúng derivations của `GET /api/v1/overview`) |
| `/help` | Danh sách lệnh |
| Nút ✅/❌ trên card | `engine.approve_action/reject_action` — cùng đường RBAC/approval/audit như Slack/Teams |

## Slack

### Setup

Dùng chung `SLACK_SIGNING_SECRET` với approval webhook. Tạo Slash Command
`/devops` trong Slack app config, Request URL:

```
https://<host>/api/v1/approvals/webhook/slack/command
```

### Lệnh

| Lệnh | Kết quả |
|------|---------|
| `/devops status` | ACK <3s ("Đang kiểm tra…"), kết quả đầy đủ gửi qua `response_url` (có guard SSRF) |
| `/devops help` / lệnh lạ | Text hướng dẫn |

## Kiến trúc

```
app/approvals/
├── chatops.py           # resolver chỉ-đọc dùng chung (tái dùng _get_*_health của overview)
├── telegram.py          # notifier: sendMessage + inline keyboard (cùng value format `approve:<id>` với Slack)
├── telegram_webhook.py  # secret-token + chat allowlist + callback/command
└── slack_command.py     # verify_slack_signature + ACK nhanh + response_url
```

An toàn: cả hai route nằm dưới prefix `/approvals/webhook/` — miễn lệch
bearer auth vì chữ ký nền tảng chính là xác thực (Slack: signing secret;
Telegram: secret token). `response_url` từ Slack được kiểm tra SSRF trước
khi POST. Lỗi 500 trả detail chung, exception đầy đủ chỉ vào log server.

## Phase B (chưa làm — điều kiện dừng rõ ràng)

Lệnh thay đổi từ chat (tạo action PENDING ngay trong chat) chỉ mở khi:
1. Có bảng map chat-user → local-user, chưa map thì từ chối;
2. Rate limit theo chat user id (không theo IP — mọi user chat chung IP platform);
3. Audit ghi cả hai định danh.
