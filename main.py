#!/usr/bin/env python3
"""
🛍️ Subzy Store — Telegram digital-products store (single file).

Run from the project root:
    set BOT_TOKEN=...        (Windows)   |   export BOT_TOKEN=...   (Linux/macOS)
    set ADMIN_IDS=111111111,222222222  (comma separated Telegram user IDs)
    python main.py

The Python dependency is declared in the project's pyproject.toml.

Disclaimer: this is a generic digital-goods store. It is NOT affiliated with or
authorised by Snapchat, Spotify, OpenAI, Google, Anthropic, NordVPN or any
provider. The store owner is responsible for making sure the products/accounts
are legitimately obtained and may be resold under the providers' terms.
"""
import asyncio
import html
import logging
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from telegram import InlineKeyboardButton as Btn
from telegram import InlineKeyboardMarkup as Kb
from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,
                          ContextTypes, MessageHandler, filters)

# ════════════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════════════
BOT_TOKEN = "8705117859:AAHQt0ZaewZzATfyM9lQR9VVw9J3jZltEr0"
ADMIN_IDS = {8353712042}
DB_PATH = os.getenv("DB_PATH", "subzy_store.db")
LANGS = ("en", "ar")
HTML = ParseMode.HTML
BROADCAST_DELAY = 0.05  # ~20 msgs/sec, safely under Telegram's ~30/sec limit

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs (incl. the bot token)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("subzy")

# ════════════════════════════════════════════════════════════════════════════
# TRANSLATIONS  (admin-panel strings are English-only; tr() falls back to "en")
# ════════════════════════════════════════════════════════════════════════════
TRANSLATIONS = {
    "en": {
        "choose_lang": "🌐 <b>Choose your language / اختر لغتك</b>",
        "welcome": "🛍️ <b>Welcome to Subzy Store!</b>\n\nPremium digital products at affordable prices.",
        "btn_store": "🛍️ Store", "btn_orders": "📦 My Orders", "btn_payments": "💳 Payment Methods",
        "btn_wallet": "💼 Wallet",
        "btn_support": "🆘 Support", "btn_settings": "⚙️ Settings",
        "btn_back": "◀️ Back", "btn_menu": "🏠 Menu", "btn_language": "🌐 Language", "btn_currency": "💱 Currency",
        "btn_continue": "✅ Continue", "btn_cancel": "❌ Cancel",
        "btn_send_proof": "📤 Send Payment Proof", "btn_cancel_order": "❌ Cancel Order",
        "btn_channel": "📢 Channel", "btn_contact": "💬 Contact Support",
        "store_title": "🛍️ <b>Store</b>\n\nChoose a product:",
        "store_empty": "No products are available right now. Please check back soon.",
        "plans_title": "<b>Plans:</b>",
        "no_plans": "No plans are available for this product right now.",
        "plan_line": "• {plan} — {price} — {stock}",
        "stock_available": "🟢 Available: {count}",
        "out_of_stock": "🔴 Out of stock",
        "out_of_stock_alert": "🔴 This plan is out of stock right now.",
        "unavailable": "This item is not available.",
        "checkout": "🛒 <b>Order Confirmation</b>\n\n<b>Product:</b>\n{product}\n\n<b>Plan:</b>\n{plan}\n\n<b>Price:</b>\n{price}\n\n<b>Stock:</b>\n{stock}",
        "choose_currency": "💱 <b>Select the currency you want to pay in:</b>",
        "cur_dzd": "🇩🇿 DZD", "cur_usd": "🇺🇸 USD",
        "choose_method": "💳 <b>Select a payment method:</b>\n\n🛍️ {item}\n💰 {amount}",
        "method_bm": "🇩🇿 BaridiMob", "method_cr": "₮ USDT",
        "method_binance": "🟡 Binance Pay", "method_wallet": "💼 Wallet",
        "no_methods": "⚠️ Payment methods are not configured yet. Please contact support.",
        "wallet_title": "💼 <b>Wallet</b>\n\nBalance: <b>{dzd}</b> · <b>{usd}</b>\n\nPending top-ups: {pending}",
        "wallet_add": "➕ Top up wallet",
        "wallet_amount_prompt": "💼 Send the amount to add in {currency} (minimum equivalent: {minimum}).",
        "wallet_amount_invalid": "⚠️ Enter a valid amount. Use up to 2 decimal places for USD and whole DZD.",
        "wallet_amount_small": "⚠️ The minimum top-up is {minimum}.",
        "wallet_amount_large": "⚠️ The maximum top-up is {maximum}.",
        "wallet_no_funding_methods": "⚠️ No wallet top-up methods are enabled yet. Please contact support.",
        "wallet_choose_method": "💼 <b>Top-up amount:</b> {amount}\n\nChoose how you will send the payment:",
        "wallet_topup_instructions": "💼 <b>Wallet top-up</b>\n\nReference: <b>{code}</b>\nAmount to send: <b>{amount}</b>\n\n{details}\n\nAfter sending, tap <b>Send Payment Proof</b>. An admin will review it before your wallet is credited.",
        "btn_topup_proof": "📤 Send Payment Proof",
        "btn_cancel_topup": "❌ Cancel Top-up",
        "wallet_topup_proof_prompt": "📤 Send the payment proof for wallet top-up <b>{code}</b> now.",
        "wallet_topup_received": "✅ <b>Top-up proof received</b>\n\nReference: <b>{code}</b>\nYour payment is under review. Your balance will change only after approval.",
        "wallet_topup_cancelled": "Top-up <b>{code}</b> was cancelled.",
        "wallet_topup_not_waiting": "⚠️ This top-up is no longer waiting for proof. Open your wallet to check its status.",
        "wallet_insufficient": "⚠️ Your wallet balance is too low. Current balance: {balance}.",
        "wallet_paid": "✅ Paid from wallet. Your order is being delivered.",
        "wallet_duplicate_click": "This wallet purchase has already been processed. Check My orders for its status.",
        "wallet_credit_notice": "✅ <b>Wallet top-up approved</b>\n\nReference: <b>{code}</b>\nCredited: <b>{amount}</b>\nNew balance: <b>{balance}</b>",
        "wallet_rejected_notice": "❌ <b>Wallet top-up rejected</b>\n\nReference: <b>{code}</b>\n{reason}Your wallet balance was not changed.",
        "topup_reject_reason": "📝 Reason: {reason}",
        "bm_details": "🇩🇿 <b>BaridiMob</b>\n📱 Account: <code>{account}</code>\n👤 Name: {name}{instr}",
        "cr_details": "₮ <b>USDT</b>\n🌐 Network: {network}\n📬 Wallet: <code>{wallet}</code>{instr}",
        "binance_details": "🟡 <b>Binance Pay</b>\n📬 Pay ID: <code>{account}</code>\n👤 Name: {name}{instr}",
        "pay_instr": "💳 <b>Payment Instructions</b>\n\n🧾 Order: <b>#{code}</b>\n🛍️ {item}\n💰 Amount to pay: <b>{amount}</b>\n\n{details}\n\nAfter paying, tap <b>Send Payment Proof</b> and upload a screenshot.",
        "send_proof_prompt": "📤 Please send your payment proof now (screenshot, photo or document) for order <b>#{code}</b>.",
        "proof_received": "✅ <b>Payment proof received</b>\n\n🧾 Order: <b>#{code}</b>\n⏳ Status: payment under review.\nYou'll be notified as soon as it's reviewed.",
        "no_pending_order": "You have no order waiting for payment. Open the 🛍️ Store to place one.",
        "order_in_review": "⏳ You already have an order for this plan under review. Please wait until it's processed.",
        "order_cancelled": "🚫 Order <b>#{code}</b> was cancelled.",
        "order_not_found": "Order not found.",
        "order_cannot_cancel": "This order can no longer be cancelled.",
        "orders_title": "📦 <b>My Orders</b>",
        "orders_empty": "You have no orders yet.",
        "order_detail": "🧾 <b>Order #{code}</b>\n\n{item}\n💰 Amount: {amount}\n💳 Payment: {method}\n📅 Date: {date}\n{status}",
        "st_pending": "⏳ Pending", "st_awaiting_payment": "💳 Awaiting Payment", "st_payment_review": "🔎 Payment Review",
        "st_completed": "✅ Completed", "st_rejected": "❌ Rejected", "st_cancelled": "🚫 Cancelled",
        "payments_title": "💳 <b>Payment Methods</b>",
        "payments_none": "Payment methods are not available yet.",
        "support_title": "🆘 <b>Support</b>\n\nNeed help with an order? Contact us: {contact}",
        "support_none": "🆘 <b>Support</b>\n\nThe support contact has not been configured yet.",
        "settings_title": "⚙️ <b>Settings</b>\n\n🌐 Language: {language}\n💱 Currency: {currency}",
        "lang_name": "English",
        "choose_cur_setting": "💱 <b>Choose your preferred currency:</b>",
        "saved": "✅ Saved",
        "banned": "🚫 Your account has been restricted. Contact support if you think this is a mistake.",
        "err_generic": "⚠️ Something went wrong. Please try again.",
        "delivery": "✅ <b>Order Completed</b>\n\nYour payment was approved.\n\n🧾 Order: <b>#{code}</b>\n{item}\n\n{content}\n\nThank you for shopping at Subzy Store! 💙",
        "delivery_email": "📧 Email: <code>{email}</code>\n🔑 Password: <code>{password}</code>",
        "delivery_raw": "📦 Details: <code>{content}</code>",
        "payment_rejected": "❌ <b>Payment Rejected</b>\n\n🧾 Order: <b>#{code}</b>\n{reason}\nIf you believe this is a mistake, please contact support.",
        "reason_line": "📝 Reason: {reason}",
        # admin notifications (translated)
        "adm_new_payment": "💳 <b>New Payment</b>\n\nOrder: <b>#{code}</b>\nCustomer: {customer}\nProduct: {product}\nPlan: {plan}\nAmount: {amount}\nPayment: {method}",
        "adm_low_stock": "⚠️ <b>LOW STOCK</b>\n\n{item}\n📦 Remaining: {count}",
        "adm_out_stock": "🔴 <b>OUT OF STOCK</b>\n\n{item}\n📦 Remaining: 0",
        "adm_delivery_failed": "⚠️ Could not deliver order <b>#{code}</b> to the customer (they may have blocked the bot). Use the button to retry.",
        # admin panel
        "a_title": "⚙️ <b>Subzy Store Admin</b>",
        "a_btn_stats": "📊 Statistics", "a_btn_products": "📦 Products", "a_btn_stock": "🗃️ Stock", "a_btn_payments": "💳 Payments",
        "a_btn_orders": "🛒 Orders", "a_btn_users": "👥 Users", "a_btn_settings": "⚙️ Settings", "a_btn_broadcast": "📢 Broadcast",
        "a_btn_topups": "💼 Wallet Top-ups",
        "a_stats": ("📊 <b>Statistics</b>\n\n<b>📅 Today</b>\n🛒 Orders: {t_orders}\n💰 Revenue: {t_rev} DA\n👥 New users: {t_users}\n"
                    "✅ Completed payments: {t_paid}\n⏳ Pending payments: {pending_pay}\n\n<b>📈 Overall</b>\n👥 Users: {users}\n🛒 Orders: {orders}\n"
                    "✅ Completed: {completed}\n⏳ Pending: {pending}\n❌ Rejected: {rejected}\n💰 Revenue: {rev} DA\n"
                    "📦 Available Stock: {avail}\n🔴 Sold Stock: {sold}"),
        "a_prods_title": "📦 <b>Products</b>\n\nSelect a product to manage it.",
        "a_btn_add_product": "➕ Add Product",
        "a_product_view": "{emoji} <b>{name}</b> — {status}\n\n🇬🇧 {den}\n🇸🇦 {dar}\n🖼️ Image: {img}\n\n<b>Plans:</b>\n{plans}",
        "a_plan_row": "• {name} / {ar} — {price} DA — 📦 {stock} — {status}",
        "a_plan_view": "{item}\n\n🇬🇧 Name: {en}\n🇸🇦 Name: {ar}\n💰 Price: {price} DA ({usd})\n📦 Available stock: {stock}\nStatus: {status}",
        "a_btn_name": "✏️ Name", "a_btn_emoji": "😀 Emoji", "a_btn_den": "📝 Description EN", "a_btn_dar": "📝 Description AR",
        "a_btn_image": "🖼️ Product Image", "a_btn_enable": "✅ Enable", "a_btn_disable": "🚫 Disable",
        "a_btn_add_plan": "➕ Add Plan", "a_btn_del_product": "🗑️ Delete Product", "a_btn_del_plan": "🗑️ Delete Plan",
        "a_btn_price": "💰 Price", "a_btn_name_en": "✏️ Name (EN)", "a_btn_name_ar": "✏️ Name (AR)",
        "a_confirm_delete": "⚠️ Delete <b>{name}</b>? This cannot be undone.", "a_btn_yes_delete": "🗑️ Yes, delete",
        "a_has_orders": "This item already has orders — disable it instead of deleting.",
        "a_deleted": "🗑️ Deleted.", "a_enabled": "Enabled", "a_disabled": "Disabled",
        "a_p_prod_add": "➕ Send the new product in this format (one message):\n\n<code>emoji | name | description EN | description AR</code>\n\nExample:\n<code>🎬 | Netflix | Premium streaming | بث مميز</code>",
        "a_p_prod_edit": "✏️ Send the new value for <b>{field}</b>:",
        "a_p_prod_img": "🖼️ Send the product image as a <b>photo</b> now.",
        "a_p_plan_add": "➕ Send the new plan in this format:\n\n<code>name EN | name AR | price in DZD</code>\n\nExample:\n<code>1 Month | شهر واحد | 1500</code>",
        "a_p_plan_edit": "✏️ Send the new value for <b>{field}</b>:",
        "a_p_stock_add": "➕ Send the stock for <b>{item}</b>: one item per line (e.g. <code>email:password</code>). You can also upload a .txt file.\n\nYour message is deleted after import.",
        "a_p_stock_rm": "🗑️ Send the stock IDs to remove for <b>{item}</b> (e.g. <code>12 13 14</code>) or <code>all</code> to remove every AVAILABLE item.",
        "a_p_cfg": "✏️ Send the new value for <b>{label}</b>.{hint}\nSend <code>-</code> to clear it (not for numbers).",
        "a_p_cfgimg": "🖼️ Send the image for <b>{label}</b> as a photo.",
        "a_p_reject": "❌ Send an optional rejection reason for the customer, or tap Skip.",
        "a_p_bc": "📢 Send the message to broadcast (text, photo, etc.).",
        "a_p_search": "🔍 Send a Telegram ID, @username or name to search.",
        "a_bad_input": "⚠️ Invalid input. Try again, or send /cancel.",
        "a_cancelled": "Cancelled.", "a_saved": "✅ Saved.",
        "a_stock_title": "🗃️ <b>Stock</b>\n\n{lines}",
        "a_btn_add_stock": "➕ Add Stock", "a_btn_view_stock": "📋 View Stock", "a_btn_rm_stock": "🗑️ Remove Stock", "a_btn_stock_stats": "📊 Stock Statistics",
        "a_pick_plan": "Choose a plan:",
        "a_stock_added": "✅ {n} stock items added.{dup}", "a_stock_dups": " ({d} duplicates skipped)",
        "a_stock_removed": "🗑️ {n} stock items removed.",
        "a_stock_view": "📋 <b>{item}</b>\n🟢 Available: {a} · 🟡 Reserved: {r} · 🔴 Sold: {s}\n\n{rows}",
        "a_stock_stats": "📊 <b>Stock Statistics</b>\n\n{lines}",
        "a_pay_title": "💳 <b>Payments</b>\n\n⏳ Pending: {n}\n\nTap a payment to review it.",
        "a_pay_none": "No pending payments. 🎉",
        "a_topups_title": "💼 <b>Wallet top-ups</b>\n\n⏳ Pending review: {n}\n\nTap a top-up to review its proof.",
        "a_topups_none": "No wallet top-ups waiting for review.",
        "a_topup_card": "💼 <b>Wallet top-up</b>\n\nReference: <b>{code}</b>\nCustomer: {customer}\nAmount: {amount}\nMethod: {method}\nRequested: {created}",
        "a_topup_approved": "✅ Wallet top-up approved and credited.",
        "a_topup_rejected": "❌ Wallet top-up rejected.",
        "a_err_topup_done": "This wallet top-up was already processed.",
        "a_binance_title": "🟡 <b>Binance Pay settings</b>\n\n📬 Pay ID: {account}\n👤 Name: {name}\n📝 Instructions: {instr}",
        "a_btn_enable_method": "✅ Enable",
        "a_btn_disable_method": "🚫 Disable",
        "a_method_not_ready": "Set the required payment details before enabling this method.",
        "a_btn_approve": "✅ Approve", "a_btn_reject": "❌ Reject", "a_btn_skip": "⏭️ Skip",
        "a_approved": "✅ Approved", "a_rejected": "❌ Rejected",
        "a_err_done": "This payment was already processed.",
        "a_err_no_stock": "⚠️ No stock available for this plan. Add stock, then approve again.",
        "a_err_banned": "⚠️ This customer is banned. Unban them first.",
        "a_err_bad_order": "⚠️ The order is no longer pending.",
        "a_orders_title": "🛒 <b>Orders</b> (latest 15)", "a_btn_only_pending": "⏳ Pending only", "a_btn_all_orders": "📋 All orders",
        "a_order_view": "🧾 <b>#{code}</b>\n\nCustomer: {customer}\n{item}\nAmount: {amount}\nPayment: {method}\nStatus: {status}\nCreated: {created}\nCompleted: {completed}",
        "a_btn_review": "🔎 Review payment", "a_btn_resend": "🔁 Resend delivery", "a_resent": "✅ Delivery sent.",
        "a_users_title": "👥 <b>Users</b>\n\nLatest users:", "a_btn_search": "🔍 Search", "a_btn_ban": "🚫 Ban", "a_btn_unban": "✅ Unban",
        "a_user_view": "👤 <b>{name}</b>\nTelegram ID: <code>{tg}</code>\nUsername: {username}\nRegistered: {date}\nOrders: {orders}\nTotal spent: {spent} DA\nWallet: {wallet}\nBanned: {banned}",
        "a_no_results": "No results.", "a_yes": "Yes", "a_no": "No", "a_set": "✅ set", "a_unset": "— not set",
        "a_bc_confirm": "📢 Send this message to all users?", "a_btn_confirm": "✅ Confirm",
        "a_bc_started": "📢 Broadcasting to {n} users…", "a_bc_done": "📢 Broadcast finished.\n✅ Sent: {ok}\n❌ Failed: {fail}",
        "a_settings_title": "⚙️ <b>Settings</b>\n\n💱 USD Rate: 1 USD = {rate} DZD\n🔔 Low-stock threshold: {thr}\n🆘 Support: {support}\n📢 Channel: {channel}\n🇩🇿 BaridiMob: {bm}\n🟡 Binance Pay: {binance}\n₮ USDT: {cr}",
        "a_bm_title": "💳 <b>BaridiMob settings</b>\n\nStatus: {enabled}\n📱 Account: {account}\n👤 Name: {name}\n📝 Instructions: {instr}\n🖼️ QR image: {qr}",
        "a_cr_title": "₮ <b>USDT settings</b>\n\nStatus: {enabled}\n🌐 Network: {network}\n📬 Wallet: {wallet}\n📝 Instructions: {instr}",
        "a_cfg_binance_account": "📬 Binance Pay ID",
        "a_cfg_binance_name": "👤 Binance account name",
        "a_cfg_binance_instructions": "📝 Binance instructions",
        "a_cfg_cr_network": "🌐 USDT network",
        "a_cfg_cr_wallet": "📬 USDT wallet address",
        "a_cfg_cr_instructions": "📝 USDT instructions",
        "a_cfg_bm_enabled": "🇩🇿 BaridiMob",
        "a_cfg_binance_enabled": "🟡 Binance Pay",
        "a_cfg_cr_enabled": "₮ USDT",
        "a_btn_clear_qr": "🗑️ Remove QR",
        "a_cfg_usd_rate": "💱 USD Rate", "a_cfg_low_stock_threshold": "🔔 Stock Threshold", "a_cfg_support_username": "🆘 Support Username",
        "a_cfg_channel": "📢 Channel", "a_cfg_bm_account": "📱 Account / Phone", "a_cfg_bm_name": "👤 Name", "a_cfg_bm_instructions": "📝 Instructions",
        "a_cfg_bm_qr": "🖼️ QR Image", "a_cfg_cr_currency": "🪙 Currency",
        "a_btn_bm": "💳 BaridiMob", "a_btn_cr": "₮ USDT", "a_btn_binance": "🟡 Binance Pay",
    },
    "ar": {
        "choose_lang": "🌐 <b>Choose your language / اختر لغتك</b>",
        "welcome": "🛍️ <b>أهلاً بك في Subzy Store!</b>\n\nمنتجات رقمية مميزة بأسعار مناسبة.",
        "btn_store": "🛍️ المتجر", "btn_orders": "📦 طلباتي", "btn_payments": "💳 طرق الدفع",
        "btn_wallet": "💼 المحفظة",
        "btn_support": "🆘 الدعم", "btn_settings": "⚙️ الإعدادات",
        "btn_back": "◀️ رجوع", "btn_menu": "🏠 القائمة", "btn_language": "🌐 اللغة", "btn_currency": "💱 العملة",
        "btn_continue": "✅ متابعة", "btn_cancel": "❌ إلغاء",
        "btn_send_proof": "📤 إرسال إثبات الدفع", "btn_cancel_order": "❌ إلغاء الطلب",
        "btn_channel": "📢 القناة", "btn_contact": "💬 تواصل مع الدعم",
        "store_title": "🛍️ <b>المتجر</b>\n\nاختر منتجاً:",
        "store_empty": "لا توجد منتجات متاحة حالياً. يرجى المحاولة لاحقاً.",
        "plans_title": "<b>الباقات:</b>",
        "no_plans": "لا توجد باقات متاحة لهذا المنتج حالياً.",
        "plan_line": "• {plan} — {price} — {stock}",
        "stock_available": "🟢 متوفر: {count}",
        "out_of_stock": "🔴 نفد المخزون",
        "out_of_stock_alert": "🔴 هذه الباقة غير متوفرة حالياً.",
        "unavailable": "هذا العنصر غير متاح.",
        "checkout": "🛒 <b>تأكيد الطلب</b>\n\n<b>المنتج:</b>\n{product}\n\n<b>الباقة:</b>\n{plan}\n\n<b>السعر:</b>\n{price}\n\n<b>المخزون:</b>\n{stock}",
        "choose_currency": "💱 <b>اختر عملة الدفع:</b>",
        "cur_dzd": "🇩🇿 DZD", "cur_usd": "🇺🇸 USD",
        "choose_method": "💳 <b>اختر طريقة الدفع:</b>\n\n🛍️ {item}\n💰 {amount}",
        "method_bm": "🇩🇿 بريدي موب", "method_cr": "₮ USDT",
        "method_binance": "🟡 Binance Pay", "method_wallet": "💼 المحفظة",
        "no_methods": "⚠️ طرق الدفع غير مُعدّة بعد. يرجى التواصل مع الدعم.",
        "wallet_title": "💼 <b>المحفظة</b>\n\nالرصيد: <b>{dzd}</b> · <b>{usd}</b>\n\nطلبات الشحن قيد المراجعة: {pending}",
        "wallet_add": "➕ شحن المحفظة",
        "wallet_amount_prompt": "💼 أرسل المبلغ الذي تريد إضافته بعملة {currency} (الحد الأدنى المكافئ: {minimum}).",
        "wallet_amount_invalid": "⚠️ أدخل مبلغاً صالحاً. استخدم منزلتين عشريتين كحد أقصى للدولار وأعداداً صحيحة للدينار.",
        "wallet_amount_small": "⚠️ الحد الأدنى للشحن هو {minimum}.",
        "wallet_amount_large": "⚠️ الحد الأقصى للشحن هو {maximum}.",
        "wallet_no_funding_methods": "⚠️ لا توجد طرق شحن مفعّلة حالياً. يرجى التواصل مع الدعم.",
        "wallet_choose_method": "💼 <b>مبلغ الشحن:</b> {amount}\n\nاختر طريقة إرسال المبلغ:",
        "wallet_topup_instructions": "💼 <b>شحن المحفظة</b>\n\nالمرجع: <b>{code}</b>\nالمبلغ المطلوب: <b>{amount}</b>\n\n{details}\n\nبعد الإرسال اضغط <b>إرسال إثبات الدفع</b>. سيراجع المسؤول الإثبات قبل إضافة الرصيد.",
        "btn_topup_proof": "📤 إرسال إثبات الدفع",
        "btn_cancel_topup": "❌ إلغاء الشحن",
        "wallet_topup_proof_prompt": "📤 أرسل إثبات دفع شحن المحفظة <b>{code}</b> الآن.",
        "wallet_topup_received": "✅ <b>تم استلام إثبات الشحن</b>\n\nالمرجع: <b>{code}</b>\nالمبلغ قيد المراجعة. لن يتغير رصيدك حتى تتم الموافقة.",
        "wallet_topup_cancelled": "تم إلغاء طلب الشحن <b>{code}</b>.",
        "wallet_topup_not_waiting": "⚠️ لم يعد طلب الشحن بانتظار الإثبات. افتح المحفظة للتحقق من حالته.",
        "wallet_insufficient": "⚠️ رصيد المحفظة غير كافٍ. رصيدك الحالي: {balance}.",
        "wallet_paid": "✅ تم الدفع من المحفظة. جارٍ تسليم طلبك.",
        "wallet_duplicate_click": "تمت معالجة هذا الشراء من المحفظة مسبقاً. تحقق من طلباتي لمعرفة حالته.",
        "wallet_credit_notice": "✅ <b>تمت الموافقة على شحن المحفظة</b>\n\nالمرجع: <b>{code}</b>\nتمت إضافة: <b>{amount}</b>\nالرصيد الجديد: <b>{balance}</b>",
        "wallet_rejected_notice": "❌ <b>تم رفض شحن المحفظة</b>\n\nالمرجع: <b>{code}</b>\n{reason}لم يتغير رصيد محفظتك.",
        "topup_reject_reason": "📝 السبب: {reason}",
        "cr_details": "₮ <b>USDT</b>\n🌐 الشبكة: {network}\n📬 المحفظة: <code>{wallet}</code>{instr}",
        "binance_details": "🟡 <b>Binance Pay</b>\n📬 معرّف الدفع: <code>{account}</code>\n👤 الاسم: {name}{instr}",
        "bm_details": "🇩🇿 <b>بريدي موب</b>\n📱 الحساب: <code>{account}</code>\n👤 الاسم: {name}{instr}",
        "pay_instr": "💳 <b>تعليمات الدفع</b>\n\n🧾 الطلب: <b>#{code}</b>\n🛍️ {item}\n💰 المبلغ المطلوب: <b>{amount}</b>\n\n{details}\n\nبعد الدفع اضغط <b>إرسال إثبات الدفع</b> وأرسل لقطة شاشة.",
        "send_proof_prompt": "📤 أرسل إثبات الدفع الآن (لقطة شاشة أو صورة أو ملف) للطلب <b>#{code}</b>.",
        "proof_received": "✅ <b>تم استلام إثبات الدفع</b>\n\n🧾 الطلب: <b>#{code}</b>\n⏳ الحالة: الدفع قيد المراجعة.\nسيتم إشعارك فور مراجعته.",
        "no_pending_order": "ليس لديك طلب بانتظار الدفع. افتح 🛍️ المتجر لإنشاء طلب.",
        "order_in_review": "⏳ لديك طلب لهذه الباقة قيد المراجعة بالفعل. يرجى الانتظار حتى تتم معالجته.",
        "order_cancelled": "🚫 تم إلغاء الطلب <b>#{code}</b>.",
        "order_not_found": "الطلب غير موجود.",
        "order_cannot_cancel": "لا يمكن إلغاء هذا الطلب الآن.",
        "orders_title": "📦 <b>طلباتي</b>",
        "orders_empty": "ليس لديك أي طلبات بعد.",
        "order_detail": "🧾 <b>الطلب #{code}</b>\n\n{item}\n💰 المبلغ: {amount}\n💳 الدفع: {method}\n📅 التاريخ: {date}\n{status}",
        "st_pending": "⏳ قيد الانتظار", "st_awaiting_payment": "💳 بانتظار الدفع", "st_payment_review": "🔎 مراجعة الدفع",
        "st_completed": "✅ مكتمل", "st_rejected": "❌ مرفوض", "st_cancelled": "🚫 ملغي",
        "payments_title": "💳 <b>طرق الدفع</b>",
        "payments_none": "طرق الدفع غير متاحة بعد.",
        "support_title": "🆘 <b>الدعم</b>\n\nهل تحتاج مساعدة بخصوص طلبك؟ تواصل معنا: {contact}",
        "support_none": "🆘 <b>الدعم</b>\n\nلم يتم إعداد وسيلة التواصل مع الدعم بعد.",
        "settings_title": "⚙️ <b>الإعدادات</b>\n\n🌐 اللغة: {language}\n💱 العملة: {currency}",
        "lang_name": "العربية",
        "choose_cur_setting": "💱 <b>اختر عملتك المفضلة:</b>",
        "saved": "✅ تم الحفظ",
        "banned": "🚫 تم تقييد حسابك. تواصل مع الدعم إن كنت تعتقد أن ذلك خطأ.",
        "err_generic": "⚠️ حدث خطأ ما. يرجى المحاولة مرة أخرى.",
        "delivery": "✅ <b>تم إكمال الطلب</b>\n\nتمت الموافقة على دفعتك.\n\n🧾 الطلب: <b>#{code}</b>\n{item}\n\n{content}\n\nشكراً لتسوقك من Subzy Store! 💙",
        "delivery_email": "📧 البريد: <code>{email}</code>\n🔑 كلمة المرور: <code>{password}</code>",
        "delivery_raw": "📦 التفاصيل: <code>{content}</code>",
        "payment_rejected": "❌ <b>تم رفض الدفع</b>\n\n🧾 الطلب: <b>#{code}</b>\n{reason}\nإذا كنت تعتقد أن هذا خطأ، يرجى التواصل مع الدعم.",
        "reason_line": "📝 السبب: {reason}",
        "adm_new_payment": "💳 <b>دفعة جديدة</b>\n\nالطلب: <b>#{code}</b>\nالعميل: {customer}\nالمنتج: {product}\nالباقة: {plan}\nالمبلغ: {amount}\nالدفع: {method}",
        "adm_low_stock": "⚠️ <b>مخزون منخفض</b>\n\n{item}\n📦 المتبقي: {count}",
        "adm_out_stock": "🔴 <b>نفد المخزون</b>\n\n{item}\n📦 المتبقي: 0",
        "adm_delivery_failed": "⚠️ تعذّر تسليم الطلب <b>#{code}</b> للعميل (ربما حظر البوت). استخدم الزر لإعادة المحاولة.",
        "a_title": "⚙️ <b>لوحة إدارة Subzy Store</b>",
        "a_btn_stats": "📊 الإحصائيات", "a_btn_products": "📦 المنتجات", "a_btn_stock": "🗃️ المخزون", "a_btn_payments": "💳 المدفوعات",
        "a_btn_orders": "🛒 الطلبات", "a_btn_users": "👥 المستخدمون", "a_btn_settings": "⚙️ الإعدادات", "a_btn_broadcast": "📢 بث",
        "a_btn_topups": "💼 شحن المحفظة", "a_btn_binance": "🟡 Binance Pay",
        "a_topups_title": "💼 <b>شحنات المحفظة</b>\n\n⏳ بانتظار المراجعة: {n}\n\nاختر طلباً لمراجعة إثبات الدفع.",
        "a_topups_none": "لا توجد شحنات محفظة بانتظار المراجعة.",
        "a_topup_card": "💼 <b>شحن المحفظة</b>\n\nالمرجع: <b>{code}</b>\nالعميل: {customer}\nالمبلغ: {amount}\nالطريقة: {method}\nتاريخ الطلب: {created}",
        "a_topup_approved": "✅ تمت الموافقة على شحن المحفظة وإضافة الرصيد.",
        "a_topup_rejected": "❌ تم رفض شحن المحفظة.",
        "a_err_topup_done": "تمت معالجة طلب شحن المحفظة مسبقاً.",
        "a_cfg_cr_wallet": "📬 عنوان محفظة USDT",
        "a_method_not_ready": "أكمل تفاصيل الدفع المطلوبة قبل تفعيل هذه الطريقة.",
        "a_btn_enable_method": "✅ تفعيل",
        "a_btn_disable_method": "🚫 تعطيل",
        "a_binance_title": "🟡 <b>إعدادات Binance Pay</b>\n\n📬 معرّف الدفع: {account}\n👤 الاسم: {name}\n📝 التعليمات: {instr}",
    },
}


def tr(lang, key, **kw):
    """Translate `key` into `lang` (falls back to English), format with kwargs.
    Arabic lines get an RLM mark so mixed LTR content (#SUB-000001, prices) renders naturally."""
    text = TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key, key)
    if kw:
        text = text.format(**kw)
    if lang == "ar":
        text = "\n".join(("\u200f" + ln) if ln.strip() else ln for ln in text.split("\n"))
    return text


# ════════════════════════════════════════════════════════════════════════════
# DATABASE
# ════════════════════════════════════════════════════════════════════════════
def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# One persistent SQLite connection avoids opening/closing a connection for every
# button press. Telegram handlers are async, but all DB calls here are synchronous
# and finish before the handler yields back to the event loop. The lock also keeps
# this safe if a future worker/thread touches the database.
_DB_CONN = None
_DB_LOCK = threading.RLock()
_SETTINGS_CACHE = {}


def _open_db():
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = sqlite3.connect(DB_PATH, timeout=30, isolation_level=None, check_same_thread=False)
        _DB_CONN.row_factory = sqlite3.Row
        _DB_CONN.execute("PRAGMA foreign_keys=ON")
        _DB_CONN.execute("PRAGMA journal_mode=WAL")
        _DB_CONN.execute("PRAGMA synchronous=NORMAL")
        _DB_CONN.execute("PRAGMA temp_store=MEMORY")
    return _DB_CONN


@contextmanager
def db():
    con = _open_db()
    with _DB_LOCK:
        yield con


@contextmanager
def tx():
    """BEGIN IMMEDIATE transaction: takes the write lock up-front -> no race conditions on stock."""
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise


def qa(sql, a=()):
    with db() as c:
        return c.execute(sql, a).fetchall()


def q1(sql, a=()):
    with db() as c:
        return c.execute(sql, a).fetchone()


def ex(sql, a=()):
    with db() as c:
        return c.execute(sql, a).lastrowid


def scalar(sql, a=()):
    r = q1(sql, a)
    return r[0] if r and r[0] is not None else 0


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER UNIQUE NOT NULL, username TEXT, first_name TEXT,
  language TEXT, currency TEXT NOT NULL DEFAULT 'dzd', banned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description_en TEXT DEFAULT '', description_ar TEXT DEFAULT '',
  emoji TEXT DEFAULT '🛍️', image_file_id TEXT, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL REFERENCES products(id),
  name_en TEXT NOT NULL, name_ar TEXT NOT NULL, price_dzd INTEGER NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS stock(
  id INTEGER PRIMARY KEY AUTOINCREMENT, plan_id INTEGER NOT NULL REFERENCES plans(id), content TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN('AVAILABLE','RESERVED','SOLD')),
  added_at TEXT NOT NULL, sold_at TEXT, order_id INTEGER);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id), plan_id INTEGER NOT NULL REFERENCES plans(id),
  stock_id INTEGER, amount_dzd INTEGER NOT NULL, amount_usd REAL NOT NULL, currency TEXT NOT NULL, payment_method TEXT,
  status TEXT NOT NULL CHECK(status IN('PENDING','AWAITING_PAYMENT','PAYMENT_REVIEW','COMPLETED','REJECTED','CANCELLED')),
  created_at TEXT NOT NULL, completed_at TEXT);
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id), method TEXT, proof_file_id TEXT,
  status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN('PENDING','APPROVED','REJECTED')),
  admin_note TEXT, created_at TEXT NOT NULL, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS wallets(
  user_id INTEGER PRIMARY KEY REFERENCES users(id), balance_dzd INTEGER NOT NULL DEFAULT 0 CHECK(balance_dzd >= 0),
  updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS wallet_topups(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
  amount_dzd INTEGER NOT NULL CHECK(amount_dzd > 0), amount_usd REAL NOT NULL CHECK(amount_usd > 0),
  rate_snapshot REAL NOT NULL CHECK(rate_snapshot > 0), input_currency TEXT NOT NULL CHECK(input_currency IN('dzd','usd')),
  method TEXT NOT NULL, proof_file_id TEXT,
  status TEXT NOT NULL CHECK(status IN('AWAITING_PROOF','PAYMENT_REVIEW','APPROVED','REJECTED','CANCELLED')),
  admin_note TEXT, created_at TEXT NOT NULL, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS wallet_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id),
  amount_dzd INTEGER NOT NULL CHECK(amount_dzd != 0), event_type TEXT NOT NULL CHECK(event_type IN('TOPUP_CREDIT','PURCHASE')),
  topup_id INTEGER REFERENCES wallet_topups(id), order_id INTEGER REFERENCES orders(id), created_at TEXT NOT NULL,
  CHECK((event_type='TOPUP_CREDIT' AND topup_id IS NOT NULL AND order_id IS NULL) OR
        (event_type='PURCHASE' AND order_id IS NOT NULL AND topup_id IS NULL)));
CREATE TABLE IF NOT EXISTS wallet_checkout_quotes(
  token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
  plan_id INTEGER NOT NULL REFERENCES plans(id), currency TEXT NOT NULL CHECK(currency IN('dzd','usd')),
  status TEXT NOT NULL CHECK(status IN('READY','COMPLETED','EXPIRED')),
  order_id INTEGER REFERENCES orders(id), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_stock_plan_status ON stock(plan_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_wallet_topups_status ON wallet_topups(status, id);
CREATE INDEX IF NOT EXISTS idx_wallet_ledger_user ON wallet_ledger(user_id, id);
CREATE INDEX IF NOT EXISTS idx_wallet_checkout_user ON wallet_checkout_quotes(user_id, plan_id, status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_topup ON wallet_ledger(topup_id) WHERE topup_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallet_ledger_order ON wallet_ledger(order_id) WHERE order_id IS NOT NULL;
"""

SEED = [  # emoji, name, desc_en, desc_ar, [(plan_en, plan_ar, price_dzd)]
    ("👻", "Snapchat Plus", "Snapchat+ premium subscription.", "اشتراك سناب شات بلس المميز.",
     [("1 Month", "شهر واحد", 850), ("1 Year", "سنة واحدة", 2600)]),
    ("🎵", "Spotify", "Spotify Premium subscription.", "اشتراك سبوتيفاي بريميوم.",
     [("1 Month", "شهر واحد", 1250), ("3 Months", "3 أشهر", 2300), ("6 Months", "6 أشهر", 3900), ("12 Months", "12 شهراً", 5500)]),
    ("✨", "Gemini", "Google Gemini Advanced subscription.", "اشتراك جيميني المتقدم من جوجل.",
     [("12 Months", "12 شهراً", 1000), ("18 Months", "18 شهراً", 1800)]),
    ("🤖", "ChatGPT Plus", "On customer's own email.", "على بريدك الإلكتروني الخاص.",
     [("1 Month", "شهر واحد", 3900)]),
    ("🚀", "ChatGPT Go", "ChatGPT Go subscription.", "اشتراك ChatGPT Go.",
     [("1 subscription", "اشتراك واحد", 2300)]),
    ("🔐", "NordVPN", "NordVPN subscription.", "اشتراك NordVPN.",
     [("3 Months", "3 أشهر", 1900)]),
    ("🧠", "Claude Pro", "Claude Pro subscription.", "اشتراك Claude Pro.",
     [("1 Month", "شهر واحد", 6000)]),
]

DEFAULT_SETTINGS = {"usd_rate": "255", "low_stock_threshold": "3", "support_username": "", "channel": "",
                    "bm_account": "", "bm_name": "", "bm_instructions": "", "bm_qr": "",
                    "bm_enabled": "0", "cr_currency": "USDT", "cr_network": "", "cr_wallet": "", "cr_instructions": "",
                    "cr_enabled": "0", "binance_account": "", "binance_name": "", "binance_instructions": "",
                    "binance_enabled": "0"}


def init_db():
    global _SETTINGS_CACHE
    with db() as c:
        c.executescript(SCHEMA)
        for k, v in DEFAULT_SETTINGS.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            for emoji, name, den, dar, plans in SEED:
                pid = c.execute("INSERT INTO products(name,description_en,description_ar,emoji) VALUES(?,?,?,?)",
                                (name, den, dar, emoji)).lastrowid
                for pen, par, price in plans:
                    c.execute("INSERT INTO plans(product_id,name_en,name_ar,price_dzd) VALUES(?,?,?,?)", (pid, pen, par, price))
        # Extra indexes for the hot order/payment lookup paths.
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_plan_status ON orders(plan_id, status, id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status, id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_payments_order_status ON payments(order_id, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_stock_order_status ON stock(order_id, status)")
        _SETTINGS_CACHE = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings").fetchall()}


# ── settings / currency ──
def get_setting(k, default=""):
    value = _SETTINGS_CACHE.get(k)
    return default if value is None else value


def set_setting(k, v):
    global _SETTINGS_CACHE
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    _SETTINGS_CACHE[k] = v


def usd_rate():
    try:
        r = float(get_setting("usd_rate", "255"))
        return r if r > 0 else 255.0
    except ValueError:
        return 255.0


def to_usd(dzd):
    return round(dzd / usd_rate(), 2)  # single conversion point


def fmt_dzd(v): return f"{int(v)} DA"
def fmt_usd(v): return f"${v:.2f}"
def fmt_both(dzd): return f"🇩🇿 {fmt_dzd(dzd)}\n🇺🇸 {fmt_usd(to_usd(dzd))}"
def fmt_inline(dzd): return f"🇩🇿 {fmt_dzd(dzd)} · 🇺🇸 {fmt_usd(to_usd(dzd))}"
def fmt_cur(dzd, cur): return fmt_usd(to_usd(dzd)) if cur == "usd" else fmt_dzd(dzd)
def h(s): return html.escape(str(s if s is not None else ""))
def order_code(oid): return f"SUB-{int(oid):06d}"
def is_admin(tg_id): return tg_id in ADMIN_IDS
def lang_of(user): return user["language"] if user["language"] in LANGS else "en"
def pick(row, base, lang): return row[f"{base}_{lang}"] or row[f"{base}_en"] or ""
def stock_count(plan_id): return scalar("SELECT COUNT(*) FROM stock WHERE plan_id=? AND status='AVAILABLE'", (plan_id,))
def stock_txt(lang, n): return tr(lang, "stock_available", count=n) if n > 0 else tr(lang, "out_of_stock")
def mask(s): return (s[:3] + "***") if len(s) > 3 else "***"
STATUS_EMOJI = {"PENDING": "⏳", "AWAITING_PAYMENT": "💳", "PAYMENT_REVIEW": "🔎", "COMPLETED": "✅", "REJECTED": "❌", "CANCELLED": "🚫"}


def upsert_user(tg):
    # One statement instead of SELECT -> INSERT/UPDATE -> SELECT.
    with db() as c:
        return c.execute(
            "INSERT INTO users(telegram_id,username,first_name,created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name "
            "RETURNING *",
            (tg.id, tg.username, tg.first_name, now()),
        ).fetchone()


def cached_user(tg, context, refresh=False):
    key = "_subzy_user"
    if not refresh:
        cached = context.user_data.get(key)
        if cached and cached.get("telegram_id") == tg.id:
            return cached
    row = upsert_user(tg)
    user = dict(row)
    context.user_data[key] = user
    return user


def admin_lang(tg_id):
    r = q1("SELECT language FROM users WHERE telegram_id=?", (tg_id,))
    return r["language"] if r and r["language"] in LANGS else "en"


PLAN_SQL = ("SELECT pl.*, p.name AS pname, p.emoji AS emoji, p.enabled AS penabled FROM plans pl "
            "JOIN products p ON p.id=pl.product_id ")
ORDER_SQL = ("SELECT o.*, pl.name_en, pl.name_ar, p.name AS pname, p.emoji AS emoji, u.telegram_id AS tg, "
             "u.username AS username, u.first_name AS first_name, u.language AS ulang FROM orders o "
             "JOIN plans pl ON pl.id=o.plan_id JOIN products p ON p.id=pl.product_id JOIN users u ON u.id=o.user_id ")


def item_label(row, lang):
    return f"{row['emoji']} {h(row['pname'])} — {h(pick(row, 'name', lang))}"


def order_amount(o): return fmt_usd(o["amount_usd"]) if o["currency"] == "usd" else fmt_dzd(o["amount_dzd"])
def payment_amount(o):
    if o["payment_method"] == "bm":
        return f"{fmt_dzd(o['amount_dzd'])} (≈ {fmt_usd(o['amount_usd'])})"
    if o["payment_method"] in ("cr", "binance"):
        suffix = " USDT" if o["payment_method"] == "cr" else ""
        return f"{fmt_usd(o['amount_usd'])}{suffix} (≈ {fmt_dzd(o['amount_dzd'])})"
    return order_amount(o)


def method_label(lang, m): return tr(lang, f"method_{m}") if m in ("bm", "cr", "binance", "wallet") else "-"


def method_is_enabled(method):
    setup = {
        "bm": bool(get_setting("bm_account")),
        "cr": bool(get_setting("cr_wallet") and get_setting("cr_network")),
        "binance": bool(get_setting("binance_account")),
    }
    return method in setup and get_setting(f"{method}_enabled", "0") == "1" and setup[method]


def available_funding_methods():
    return [method for method in ("bm", "binance", "cr") if method_is_enabled(method)]


def customer_str(o):
    name = f"@{h(o['username'])}" if o["username"] else h(o["first_name"] or "-")
    return f"{name} (<code>{o['tg']}</code>)"


# ── order / payment / stock logic (all transaction-safe) ──
def create_order(user_id, plan_id, cur, method):
    with tx() as c:
        pl = c.execute(PLAN_SQL + "WHERE pl.id=?", (plan_id,)).fetchone()
        if not pl or not pl["enabled"] or not pl["penabled"]:
            return "unavailable", None
        avail = c.execute("SELECT COUNT(*) FROM stock WHERE plan_id=? AND status='AVAILABLE'", (plan_id,)).fetchone()[0]
        if avail == 0:
            return "out_of_stock", None
        usd = to_usd(pl["price_dzd"])
        ex_o = c.execute("SELECT id,status FROM orders WHERE user_id=? AND plan_id=? AND status IN('AWAITING_PAYMENT','PAYMENT_REVIEW') "
                         "ORDER BY id DESC LIMIT 1", (user_id, plan_id)).fetchone()
        if ex_o:  # duplicate-order protection
            if ex_o["status"] == "PAYMENT_REVIEW":
                return "in_review", ex_o["id"]
            c.execute("UPDATE orders SET currency=?, payment_method=?, amount_dzd=?, amount_usd=? WHERE id=?",
                      (cur, method, pl["price_dzd"], usd, ex_o["id"]))
            return "ok", ex_o["id"]
        oid = c.execute("INSERT INTO orders(user_id,plan_id,amount_dzd,amount_usd,currency,payment_method,status,created_at) "
                        "VALUES(?,?,?,?,?,?,'AWAITING_PAYMENT',?)",
                        (user_id, plan_id, pl["price_dzd"], usd, cur, method, now())).lastrowid
        return "ok", oid


def submit_proof(user_id, oid, proof):
    with tx() as c:
        o = c.execute("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, user_id)).fetchone()
        if not o or o["status"] != "AWAITING_PAYMENT":
            return None
        c.execute("UPDATE orders SET status='PAYMENT_REVIEW' WHERE id=?", (oid,))
        return c.execute("INSERT INTO payments(order_id,method,proof_file_id,status,created_at) VALUES(?,?,?,'PENDING',?)",
                         (oid, o["payment_method"], proof, now())).lastrowid


def approve_payment(pid):
    """Verify -> reserve -> approve -> SOLD -> complete, all in ONE transaction (no double sale)."""
    with tx() as c:
        pay = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        if not pay or pay["status"] != "PENDING":
            return ("done", None)
        o = c.execute("SELECT * FROM orders WHERE id=?", (pay["order_id"],)).fetchone()
        if not o or o["status"] != "PAYMENT_REVIEW":
            return ("bad_order", None)
        u = c.execute("SELECT * FROM users WHERE id=?", (o["user_id"],)).fetchone()
        if u["banned"]:
            return ("banned", None)
        st = c.execute("SELECT id FROM stock WHERE plan_id=? AND status='AVAILABLE' ORDER BY id LIMIT 1", (o["plan_id"],)).fetchone()
        if not st:
            return ("no_stock", None)
        if c.execute("UPDATE stock SET status='RESERVED', order_id=? WHERE id=? AND status='AVAILABLE'", (o["id"], st["id"])).rowcount != 1:
            return ("no_stock", None)
        t = now()
        c.execute("UPDATE payments SET status='APPROVED', reviewed_at=? WHERE id=?", (t, pid))
        c.execute("UPDATE stock SET status='SOLD', sold_at=? WHERE id=? AND status='RESERVED'", (t, st["id"]))
        c.execute("UPDATE orders SET status='COMPLETED', stock_id=?, completed_at=? WHERE id=? AND status='PAYMENT_REVIEW'",
                  (st["id"], t, o["id"]))
        return ("ok", {"order_id": o["id"], "plan_id": o["plan_id"]})


def reject_payment(pid, note):
    with tx() as c:
        pay = c.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        if not pay or pay["status"] != "PENDING":
            return None
        c.execute("UPDATE payments SET status='REJECTED', admin_note=?, reviewed_at=? WHERE id=?", (note, now(), pid))
        c.execute("UPDATE orders SET status='REJECTED' WHERE id=? AND status='PAYMENT_REVIEW'", (pay["order_id"],))
        return pay["order_id"]


def wallet_balance_dzd(user_id):
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO wallets(user_id,balance_dzd,updated_at) VALUES(?,0,?)", (user_id, now()))
        row = c.execute("SELECT balance_dzd FROM wallets WHERE user_id=?", (user_id,)).fetchone()
        return int(row["balance_dzd"])


def create_wallet_checkout_quote(user_id, plan_id, currency):
    if currency not in ("dzd", "usd"):
        return None
    token = secrets.token_urlsafe(8)
    with tx() as c:
        plan = c.execute(PLAN_SQL + "WHERE pl.id=?", (plan_id,)).fetchone()
        if not plan or not plan["enabled"] or not plan["penabled"]:
            return None
        stock = c.execute(
            "SELECT 1 FROM stock WHERE plan_id=? AND status='AVAILABLE' LIMIT 1", (plan_id,)
        ).fetchone()
        if not stock:
            return None
        c.execute("INSERT OR IGNORE INTO wallets(user_id,balance_dzd,updated_at) VALUES(?,0,?)", (user_id, now()))
        balance = c.execute("SELECT balance_dzd FROM wallets WHERE user_id=?", (user_id,)).fetchone()[0]
        if balance < plan["price_dzd"]:
            return None
        c.execute(
            "UPDATE wallet_checkout_quotes SET status='EXPIRED' "
            "WHERE user_id=? AND plan_id=? AND status='READY'",
            (user_id, plan_id),
        )
        c.execute(
            "DELETE FROM wallet_checkout_quotes WHERE status='EXPIRED' "
            "AND datetime(created_at)<datetime('now','-30 days')"
        )
        c.execute(
            "INSERT INTO wallet_checkout_quotes(token,user_id,plan_id,currency,status,created_at) "
            "VALUES(?,?,?,?, 'READY',?)",
            (token, user_id, plan_id, currency, now()),
        )
    return token


def wallet_topup_code(topup_id):
    return f"WAL-{int(topup_id):06d}"


def parse_wallet_topup_amount(raw, currency):
    """Return (DZD integer, USD float, error key)."""
    text = (raw or "").strip().replace(",", ".")
    if not re.fullmatch(r"\d{1,9}(?:\.\d{1,2})?", text):
        return None, None, "wallet_amount_invalid"
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None, None, "wallet_amount_invalid"
    if amount <= 0:
        return None, None, "wallet_amount_invalid"
    rate = Decimal(str(usd_rate()))
    if currency == "usd":
        amount_dzd = int((amount * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    elif currency == "dzd":
        if amount != amount.to_integral_value():
            return None, None, "wallet_amount_invalid"
        amount_dzd = int(amount)
    else:
        return None, None, "wallet_amount_invalid"
    if amount_dzd < 100:
        return None, None, "wallet_amount_small"
    if amount_dzd > 25_000_000:
        return None, None, "wallet_amount_large"
    return amount_dzd, round(amount_dzd / float(rate), 2), None


def create_wallet_topup(user_id, amount_dzd, amount_usd, currency, method):
    with tx() as c:
        c.execute("INSERT OR IGNORE INTO wallets(user_id,balance_dzd,updated_at) VALUES(?,0,?)", (user_id, now()))
        cur = c.execute(
            "INSERT INTO wallet_topups(user_id,amount_dzd,amount_usd,rate_snapshot,input_currency,method,status,created_at) "
            "VALUES(?,?,?,?,?,?,'AWAITING_PROOF',?)",
            (user_id, int(amount_dzd), float(amount_usd), usd_rate(), currency, method, now()),
        )
        return cur.lastrowid


def submit_wallet_topup_proof(user_id, topup_id, proof):
    with tx() as c:
        cur = c.execute(
            "UPDATE wallet_topups SET proof_file_id=?,status='PAYMENT_REVIEW' "
            "WHERE id=? AND user_id=? AND status='AWAITING_PROOF'",
            (proof, topup_id, user_id),
        )
        return cur.rowcount == 1


def cancel_wallet_topup(user_id, topup_id):
    with tx() as c:
        cur = c.execute(
            "UPDATE wallet_topups SET status='CANCELLED' "
            "WHERE id=? AND user_id=? AND status='AWAITING_PROOF'",
            (topup_id, user_id),
        )
        return cur.rowcount == 1


def approve_wallet_topup(topup_id):
    """Approve and credit a top-up exactly once, atomically recording its ledger entry."""
    with tx() as c:
        topup = c.execute(
            "SELECT * FROM wallet_topups WHERE id=? AND status='PAYMENT_REVIEW'", (topup_id,)
        ).fetchone()
        if not topup:
            return None
        c.execute("INSERT OR IGNORE INTO wallets(user_id,balance_dzd,updated_at) VALUES(?,0,?)",
                  (topup["user_id"], now()))
        changed = c.execute(
            "UPDATE wallet_topups SET status='APPROVED',reviewed_at=? WHERE id=? AND status='PAYMENT_REVIEW'",
            (now(), topup_id),
        ).rowcount
        if changed != 1:
            return None
        c.execute(
            "UPDATE wallets SET balance_dzd=balance_dzd+?,updated_at=? WHERE user_id=?",
            (topup["amount_dzd"], now(), topup["user_id"]),
        )
        c.execute(
            "INSERT INTO wallet_ledger(user_id,amount_dzd,event_type,topup_id,created_at) "
            "VALUES(?,?,'TOPUP_CREDIT',?,?)",
            (topup["user_id"], topup["amount_dzd"], topup_id, now()),
        )
        user = c.execute("SELECT telegram_id,language FROM users WHERE id=?", (topup["user_id"],)).fetchone()
        balance = c.execute("SELECT balance_dzd FROM wallets WHERE user_id=?", (topup["user_id"],)).fetchone()[0]
        return {"telegram_id": user["telegram_id"], "language": user["language"],
                "amount_dzd": topup["amount_dzd"], "amount_usd": topup["amount_usd"],
                "balance_dzd": balance, "topup_id": topup_id}


def reject_wallet_topup(topup_id, note):
    with tx() as c:
        topup = c.execute(
            "SELECT user_id FROM wallet_topups WHERE id=? AND status='PAYMENT_REVIEW'", (topup_id,)
        ).fetchone()
        if not topup:
            return None
        changed = c.execute(
            "UPDATE wallet_topups SET status='REJECTED',admin_note=?,reviewed_at=? "
            "WHERE id=? AND status='PAYMENT_REVIEW'",
            (note, now(), topup_id),
        ).rowcount
        if changed != 1:
            return None
        user = c.execute("SELECT telegram_id,language FROM users WHERE id=?", (topup["user_id"],)).fetchone()
        return {"telegram_id": user["telegram_id"], "language": user["language"], "topup_id": topup_id}


def buy_with_wallet(user_id, plan_id, currency, checkout_token):
    """Charge once per checkout token and mark stock sold in the same transaction."""
    with tx() as c:
        quote = c.execute(
            "SELECT status,order_id,datetime(created_at,'+15 minutes')>datetime('now') AS is_fresh "
            "FROM wallet_checkout_quotes "
            "WHERE token=? AND user_id=? AND plan_id=? AND currency=?",
            (checkout_token, user_id, plan_id, currency),
        ).fetchone()
        if not quote:
            return "invalid", None
        if quote["status"] == "COMPLETED":
            return "already_processed", None
        if quote["status"] != "READY":
            return "invalid", None
        if not quote["is_fresh"]:
            c.execute("UPDATE wallet_checkout_quotes SET status='EXPIRED' WHERE token=?", (checkout_token,))
            return "invalid", None
        pl = c.execute(PLAN_SQL + "WHERE pl.id=?", (plan_id,)).fetchone()
        if not pl or not pl["enabled"] or not pl["penabled"]:
            c.execute("UPDATE wallet_checkout_quotes SET status='EXPIRED' WHERE token=?", (checkout_token,))
            return "unavailable", None
        stock = c.execute(
            "SELECT id FROM stock WHERE plan_id=? AND status='AVAILABLE' ORDER BY id LIMIT 1",
            (plan_id,),
        ).fetchone()
        if not stock:
            c.execute("UPDATE wallet_checkout_quotes SET status='EXPIRED' WHERE token=?", (checkout_token,))
            return "out_of_stock", None
        c.execute("INSERT OR IGNORE INTO wallets(user_id,balance_dzd,updated_at) VALUES(?,0,?)", (user_id, now()))
        charged = c.execute(
            "UPDATE wallets SET balance_dzd=balance_dzd-?,updated_at=? "
            "WHERE user_id=? AND balance_dzd>=?",
            (pl["price_dzd"], now(), user_id, pl["price_dzd"]),
        ).rowcount
        if charged != 1:
            balance = c.execute("SELECT balance_dzd FROM wallets WHERE user_id=?", (user_id,)).fetchone()[0]
            c.execute("UPDATE wallet_checkout_quotes SET status='EXPIRED' WHERE token=?", (checkout_token,))
            return "insufficient", int(balance)
        t = now()
        oid = c.execute(
            "INSERT INTO orders(user_id,plan_id,stock_id,amount_dzd,amount_usd,currency,payment_method,status,created_at,completed_at) "
            "VALUES(?,?,?,?,?,?,'wallet','COMPLETED',?,?)",
            (user_id, plan_id, stock["id"], pl["price_dzd"], to_usd(pl["price_dzd"]), currency, t, t),
        ).lastrowid
        sold = c.execute(
            "UPDATE stock SET status='SOLD',sold_at=?,order_id=? WHERE id=? AND status='AVAILABLE'",
            (t, oid, stock["id"]),
        ).rowcount
        if sold != 1:
            raise RuntimeError("Wallet purchase failed to reserve stock")
        c.execute(
            "INSERT INTO wallet_ledger(user_id,amount_dzd,event_type,order_id,created_at) "
            "VALUES(?,?,'PURCHASE',?,?)",
            (user_id, -int(pl["price_dzd"]), oid, t),
        )
        changed = c.execute(
            "UPDATE wallet_checkout_quotes SET status='COMPLETED',order_id=? WHERE token=? AND status='READY'",
            (oid, checkout_token),
        ).rowcount
        if changed != 1:
            raise RuntimeError("Wallet checkout token was already consumed")
        return "ok", {"order_id": oid, "plan_id": plan_id}


def add_stock(plan_id, lines):
    with tx() as c:
        existing = {r[0] for r in c.execute("SELECT content FROM stock WHERE plan_id=? AND status='AVAILABLE'", (plan_id,))}
        added = dup = 0
        t = now()
        for line in lines:
            if line in existing:
                dup += 1
                continue
            existing.add(line)
            c.execute("INSERT INTO stock(plan_id,content,status,added_at) VALUES(?,?,'AVAILABLE',?)", (plan_id, line, t))
            added += 1
    return added, dup


# ════════════════════════════════════════════════════════════════════════════
# VIEWS  (each returns (text, markup, photo_file_id))
# ════════════════════════════════════════════════════════════════════════════
def back_row(lang, data): return [Btn(tr(lang, "btn_back"), callback_data=data)]


def v_lang_choice(from_settings=False):
    suf = ":s" if from_settings else ""
    kb = [[Btn("🇬🇧 English", callback_data=f"lang:en{suf}"), Btn("🇸🇦 العربية", callback_data=f"lang:ar{suf}")]]
    if from_settings:
        kb.append(back_row("en", "m:settings"))
    return tr("en", "choose_lang"), Kb(kb), None


def v_main(lang):
    t = lambda k: tr(lang, k)
    kb = Kb([[Btn(t("btn_store"), callback_data="m:store")],
             [Btn(t("btn_orders"), callback_data="m:orders"), Btn(t("btn_wallet"), callback_data="m:wallet")],
             [Btn(t("btn_payments"), callback_data="m:pay")],
             [Btn(t("btn_support"), callback_data="m:support"), Btn(t("btn_settings"), callback_data="m:settings")]])
    return tr(lang, "welcome"), kb, None


def v_store(lang):
    rows = qa("SELECT p.*, (SELECT COUNT(*) FROM stock s JOIN plans pl ON pl.id=s.plan_id WHERE pl.product_id=p.id "
              "AND pl.enabled=1 AND s.status='AVAILABLE') AS avail FROM products p WHERE p.enabled=1 ORDER BY p.id")
    if not rows:
        return tr(lang, "store_empty"), Kb([back_row(lang, "m:main")]), None
    kb = [[Btn(f"{r['emoji']} {r['name']}" + ("" if r["avail"] else " 🔴"), callback_data=f"p:{r['id']}")] for r in rows]
    kb.append(back_row(lang, "m:main"))
    return tr(lang, "store_title"), Kb(kb), None


def v_product(lang, user, pid):
    p = q1("SELECT * FROM products WHERE id=? AND enabled=1", (pid,))
    if not p:
        return v_store(lang)
    plans = qa("SELECT pl.*, (SELECT COUNT(*) FROM stock s WHERE s.plan_id=pl.id AND s.status='AVAILABLE') AS avail "
               "FROM plans pl WHERE pl.product_id=? AND pl.enabled=1 ORDER BY pl.id", (pid,))
    lines = [f"{p['emoji']} <b>{h(p['name'])}</b>"]
    desc = pick(p, "description", lang)
    if desc:
        lines.append(h(desc))
    lines.append("")
    kb = []
    if plans:
        lines.append(tr(lang, "plans_title"))
        for pl in plans:
            lines.append(tr(lang, "plan_line", plan=h(pick(pl, "name", lang)), price=fmt_inline(pl["price_dzd"]), stock=stock_txt(lang, pl["avail"])))
            kb.append([Btn(f"{pick(pl, 'name', lang)} — {fmt_cur(pl['price_dzd'], user['currency'])} {'🟢' if pl['avail'] else '🔴'}",
                           callback_data=f"pl:{pl['id']}")])
    else:
        lines.append(tr(lang, "no_plans"))
    kb.append(back_row(lang, "m:store"))
    return "\n".join(lines), Kb(kb), p["image_file_id"]


def v_checkout(lang, pl):
    text = tr(lang, "checkout", product=f"{pl['emoji']} {h(pl['pname'])}", plan=h(pick(pl, "name", lang)),
              price=fmt_both(pl["price_dzd"]), stock=stock_txt(lang, stock_count(pl["id"])))
    kb = Kb([[Btn(tr(lang, "btn_continue"), callback_data=f"co:{pl['id']}"), Btn(tr(lang, "btn_cancel"), callback_data="m:store")]])
    return text, kb, None


def v_currency(lang, pl):
    kb = Kb([[Btn(tr(lang, "cur_dzd"), callback_data=f"oc:{pl['id']}:dzd"), Btn(tr(lang, "cur_usd"), callback_data=f"oc:{pl['id']}:usd")],
             back_row(lang, f"pl:{pl['id']}")])
    return tr(lang, "choose_currency"), kb, None


def v_method(lang, pl, cur, user_id, checkout_token=None):
    kb = []
    if method_is_enabled("bm"):
        kb.append([Btn(tr(lang, "method_bm"), callback_data=f"om:{pl['id']}:{cur}:bm")])
    if method_is_enabled("binance"):
        kb.append([Btn(tr(lang, "method_binance"), callback_data=f"om:{pl['id']}:{cur}:binance")])
    if method_is_enabled("cr"):
        kb.append([Btn(tr(lang, "method_cr"), callback_data=f"om:{pl['id']}:{cur}:cr")])
    balance = wallet_balance_dzd(user_id)
    if balance >= pl["price_dzd"] and checkout_token:
        kb.append([Btn(f"{tr(lang, 'method_wallet')} — {fmt_cur(balance, cur)}",
                       callback_data=f"om:{pl['id']}:{cur}:wallet:{checkout_token}")])
    kb.append(back_row(lang, f"co:{pl['id']}"))
    if len(kb) == 1:
        return tr(lang, "no_methods"), Kb(kb), None
    text = tr(lang, "choose_method", item=item_label(pl, lang), amount=fmt_cur(pl["price_dzd"], cur))
    return text, Kb(kb), None


def v_wallet(lang, user):
    balance = wallet_balance_dzd(user["id"])
    pending = scalar(
        "SELECT COUNT(*) FROM wallet_topups WHERE user_id=? AND status IN('AWAITING_PROOF','PAYMENT_REVIEW')",
        (user["id"],),
    )
    text = tr(lang, "wallet_title", dzd=fmt_dzd(balance), usd=fmt_usd(to_usd(balance)), pending=pending)
    return text, Kb([[Btn(tr(lang, "wallet_add"), callback_data="w:add")],
                     back_row(lang, "m:main")]), None


def v_wallet_funding_methods(lang, amount_dzd, amount_usd, currency):
    methods = available_funding_methods()
    amount = fmt_usd(amount_usd) if currency == "usd" else fmt_dzd(amount_dzd)
    kb = [[Btn(tr(lang, f"method_{method}"), callback_data=f"wtm:{method}")]
          for method in methods]
    kb.append(back_row(lang, "m:wallet"))
    if not methods:
        return tr(lang, "wallet_no_funding_methods"), Kb(kb), None
    return tr(lang, "wallet_choose_method", amount=amount), Kb(kb), None


def method_details(lang, m):
    if m == "bm":
        acc = get_setting("bm_account")
        if not acc:
            return ""
        ins = get_setting("bm_instructions")
        return tr(lang, "bm_details", account=h(acc), name=h(get_setting("bm_name") or "-"), instr=("\n\n" + h(ins)) if ins else "")
    if m == "cr":
        w = get_setting("cr_wallet")
        network = get_setting("cr_network")
        if not w or not network:
            return ""
        ins = get_setting("cr_instructions")
        return tr(lang, "cr_details", network=h(network), wallet=h(w), instr=("\n\n" + h(ins)) if ins else "")
    if m == "binance":
        account = get_setting("binance_account")
        if not account:
            return ""
        ins = get_setting("binance_instructions")
        return tr(lang, "binance_details", account=h(account), name=h(get_setting("binance_name") or "-"),
                  instr=("\n\n" + h(ins)) if ins else "")
    return ""


def v_wallet_topup_instructions(lang, topup):
    code = wallet_topup_code(topup["id"])
    if topup["method"] == "bm":
        amount = fmt_dzd(topup["amount_dzd"])
    else:
        suffix = " USDT" if topup["method"] == "cr" else ""
        amount = f"{fmt_usd(topup['amount_usd'])}{suffix} (≈ {fmt_dzd(topup['amount_dzd'])})"
    text = tr(lang, "wallet_topup_instructions", code=code, amount=amount,
              details=method_details(lang, topup["method"]))
    kb = Kb([[Btn(tr(lang, "btn_topup_proof"), callback_data=f"wtp:{topup['id']}")],
             [Btn(tr(lang, "btn_cancel_topup"), callback_data=f"wtc:{topup['id']}")]])
    photo = (get_setting("bm_qr") or None) if topup["method"] == "bm" else None
    return text, kb, photo


def v_instructions(lang, o):
    text = tr(lang, "pay_instr", code=order_code(o["id"]), item=item_label(o, lang), amount=payment_amount(o),
              details=method_details(lang, o["payment_method"]))
    kb = Kb([[Btn(tr(lang, "btn_send_proof"), callback_data=f"proof:{o['id']}")],
             [Btn(tr(lang, "btn_cancel_order"), callback_data=f"cancel:{o['id']}")]])
    photo = (get_setting("bm_qr") or None) if o["payment_method"] == "bm" else None
    return text, kb, photo


def v_orders(lang, user):
    rows = qa(ORDER_SQL + "WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (user["id"],))
    if not rows:
        return tr(lang, "orders_empty"), Kb([back_row(lang, "m:main")]), None
    blocks, kb = [tr(lang, "orders_title"), ""], []
    for o in rows:
        blocks.append(f"<b>#{order_code(o['id'])}</b>\n{item_label(o, lang)}\n💰 {order_amount(o)}\n{tr(lang, 'st_' + o['status'].lower())}\n")
        kb.append([Btn(f"#{order_code(o['id'])} {STATUS_EMOJI[o['status']]}", callback_data=f"ord:{o['id']}")])
    kb.append(back_row(lang, "m:main"))
    return "\n".join(blocks), Kb(kb), None


def v_order(lang, user, oid):
    o = q1(ORDER_SQL + "WHERE o.id=? AND o.user_id=?", (oid, user["id"]))
    if not o:
        return tr(lang, "order_not_found"), Kb([back_row(lang, "m:orders")]), None
    text = tr(lang, "order_detail", code=order_code(o["id"]), item=item_label(o, lang), amount=order_amount(o),
              method=method_label(lang, o["payment_method"]), date=o["created_at"][:16], status=tr(lang, "st_" + o["status"].lower()))
    kb = []
    if o["status"] == "AWAITING_PAYMENT":
        kb += [[Btn(tr(lang, "btn_send_proof"), callback_data=f"proof:{o['id']}")], [Btn(tr(lang, "btn_cancel_order"), callback_data=f"cancel:{o['id']}")]]
    kb.append(back_row(lang, "m:orders"))
    return text, Kb(kb), None


def v_payments(lang):
    parts = [method_details(lang, m) for m in available_funding_methods()]
    parts = [part for part in parts if part]
    if not parts:
        return tr(lang, "payments_none"), Kb([back_row(lang, "m:main")]), None
    photo = (get_setting("bm_qr") or None) if method_is_enabled("bm") else None
    return tr(lang, "payments_title") + "\n\n" + "\n\n".join(parts), Kb([back_row(lang, "m:main")]), photo


def v_support(lang):
    sup, ch = get_setting("support_username"), get_setting("channel")
    kb = []
    if sup:
        kb.append([Btn(tr(lang, "btn_contact"), url=f"https://t.me/{sup}")])
    if ch:
        kb.append([Btn(tr(lang, "btn_channel"), url=f"https://t.me/{ch}")])
    kb.append(back_row(lang, "m:main"))
    text = tr(lang, "support_title", contact=f"@{h(sup)}") if sup else tr(lang, "support_none")
    return text, Kb(kb), None


def v_settings(lang, user):
    text = tr(lang, "settings_title", language=tr(lang, "lang_name"), currency=tr(lang, "cur_" + user["currency"]))
    kb = Kb([[Btn(tr(lang, "btn_language"), callback_data="s:lang"), Btn(tr(lang, "btn_currency"), callback_data="s:cur")],
             [Btn(tr(lang, "btn_support"), callback_data="m:support")], back_row(lang, "m:main")])
    return text, kb, None


# ── Telegram output helpers ──
async def send_view(chat, view):
    text, markup, photo = view
    if photo:
        try:
            return await chat.send_photo(photo, caption=text, reply_markup=markup, parse_mode=HTML)
        except BadRequest:
            logger.warning("send_photo failed (bad file_id?) – falling back to text")
    return await chat.send_message(text, reply_markup=markup, parse_mode=HTML)


async def show(q, view):
    """Render a view in place of the callback's message (edit when possible, else delete+send)."""
    text, markup, photo = view
    msg = q.message
    if msg.text and not photo:
        try:
            await msg.edit_text(text, reply_markup=markup, parse_mode=HTML)
            return
        except BadRequest as e:
            if "not modified" in str(e).lower():
                return
    try:
        await msg.delete()
    except TelegramError:
        pass
    await send_view(msg.chat, view)


async def notify_admins(bot, key, markup=None, **kw):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, tr(admin_lang(aid), key, **kw), parse_mode=HTML, reply_markup=markup)
        except TelegramError:
            logger.warning("could not notify admin %s", aid)


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT REVIEW / DELIVERY / ALERTS
# ════════════════════════════════════════════════════════════════════════════
def payment_card(al, pid):
    pay = q1("SELECT * FROM payments WHERE id=?", (pid,))
    if not pay:
        return None
    o = q1(ORDER_SQL + "WHERE o.id=?", (pay["order_id"],))
    amt = payment_amount(o)
    text = tr(al, "adm_new_payment", code=order_code(o["id"]), customer=customer_str(o), product=f"{o['emoji']} {h(o['pname'])}",
              plan=h(pick(o, "name", al)), amount=amt, method=method_label(al, pay["method"]))
    kb = None
    if pay["status"] == "PENDING":
        kb = Kb([[Btn(tr(al, "a_btn_approve"), callback_data=f"A:pa:{pid}"), Btn(tr(al, "a_btn_reject"), callback_data=f"A:pr:{pid}")]])
    return text, kb, pay["proof_file_id"] or ""


async def send_payment_card(bot, chat_id, al, pid):
    card = payment_card(al, pid)
    if not card:
        return
    text, kb, proof = card
    kind, _, fid = proof.partition(":")
    if kind == "photo" and fid:
        await bot.send_photo(chat_id, fid, caption=text, reply_markup=kb, parse_mode=HTML)
    elif kind == "doc" and fid:
        await bot.send_document(chat_id, fid, caption=text, reply_markup=kb, parse_mode=HTML)
    else:
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode=HTML)


async def notify_admins_payment(bot, pid):
    for aid in ADMIN_IDS:
        try:
            await send_payment_card(bot, aid, admin_lang(aid), pid)
        except TelegramError:
            logger.warning("could not send payment card to admin %s", aid)


async def deliver(bot, oid):
    """Send purchased content ONLY to the customer's private chat. Credentials are never logged."""
    o = q1(ORDER_SQL + "WHERE o.id=? AND o.status='COMPLETED'", (oid,))
    if not o or not o["stock_id"]:
        return False
    st = q1("SELECT content FROM stock WHERE id=? AND order_id=? AND status='SOLD'", (o["stock_id"], oid))
    if not st:
        return False
    lang = o["ulang"] if o["ulang"] in LANGS else "en"
    m = re.match(r"^([^\s:]+@[^\s:]+):(.+)$", st["content"].strip(), re.S)
    body = tr(lang, "delivery_email", email=h(m.group(1)), password=h(m.group(2))) if m else tr(lang, "delivery_raw", content=h(st["content"]))
    try:
        await bot.send_message(o["tg"], tr(lang, "delivery", code=order_code(oid), item=item_label(o, lang), content=body), parse_mode=HTML)
        return True
    except TelegramError as e:
        logger.warning("delivery failed for order %s: %s", oid, type(e).__name__)
        return False


async def check_low_stock(bot, plan_id):
    n, thr = stock_count(plan_id), scalar("SELECT CAST(? AS INTEGER)", (get_setting("low_stock_threshold", "3"),))
    if n > thr:
        return
    pl = q1(PLAN_SQL + "WHERE pl.id=?", (plan_id,))
    for aid in ADMIN_IDS:
        al = admin_lang(aid)
        try:
            if n == 0:
                await bot.send_message(aid, tr(al, "adm_out_stock", item=item_label(pl, al)), parse_mode=HTML)
            else:
                await bot.send_message(aid, tr(al, "adm_low_stock", item=item_label(pl, al), count=n), parse_mode=HTML)
        except TelegramError:
            pass


# ════════════════════════════════════════════════════════════════════════════
# USER CALLBACKS
# ════════════════════════════════════════════════════════════════════════════
async def user_cb(q, context, user, p):
    lang = lang_of(user)
    a = p[0]
    if a == "lang" and len(p) > 1 and p[1] in LANGS:
        ex("UPDATE users SET language=? WHERE id=?", (p[1], user["id"]))
        user["language"] = p[1]
        context.user_data["_subzy_user"] = user
        await show(q, v_settings(p[1], user) if len(p) > 2 else v_main(p[1]))
    elif a == "m" and len(p) > 1:
        for key in ("wallet_topup_currency", "wallet_topup_amount_dzd", "wallet_topup_amount_usd"):
            context.user_data.pop(key, None)
        v = {"main": lambda: v_main(lang), "store": lambda: v_store(lang), "orders": lambda: v_orders(lang, user),
             "pay": lambda: v_payments(lang), "wallet": lambda: v_wallet(lang, user),
             "support": lambda: v_support(lang), "settings": lambda: v_settings(lang, user)}.get(p[1])
        if v:
            await show(q, v())
    elif a == "w" and len(p) > 1 and p[1] == "add":
        for key in ("wallet_topup_amount_dzd", "wallet_topup_amount_usd"):
            context.user_data.pop(key, None)
        if not available_funding_methods():
            await show(q, (tr(lang, "wallet_no_funding_methods"),
                           Kb([back_row(lang, "m:wallet")]), None))
        else:
            context.user_data["wallet_topup_currency"] = user["currency"]
            currency = tr(lang, "cur_" + user["currency"])
            minimum = (fmt_usd((Decimal(100) / Decimal(str(usd_rate()))).quantize(Decimal("0.01"), rounding=ROUND_CEILING))
                       if user["currency"] == "usd" else fmt_dzd(100))
            await q.message.chat.send_message(
                tr(lang, "wallet_amount_prompt", currency=currency, minimum=minimum),
                parse_mode=HTML,
            )
    elif a == "s" and len(p) > 1:
        if p[1] == "lang":
            await show(q, v_lang_choice(True))
        elif p[1] == "cur":
            kb = Kb([[Btn(tr(lang, "cur_dzd"), callback_data="cur:dzd"), Btn(tr(lang, "cur_usd"), callback_data="cur:usd")], back_row(lang, "m:settings")])
            await show(q, (tr(lang, "choose_cur_setting"), kb, None))
    elif a == "cur" and len(p) > 1 and p[1] in ("dzd", "usd"):
        ex("UPDATE users SET currency=? WHERE id=?", (p[1], user["id"]))
        user["currency"] = p[1]
        context.user_data["_subzy_user"] = user
        await show(q, v_settings(lang, user))
        return tr(lang, "saved")
    elif a == "p":
        await show(q, v_product(lang, user, int(p[1])))
    elif a in ("pl", "co", "oc", "om"):
        pl = q1(PLAN_SQL + "WHERE pl.id=?", (int(p[1]),))
        if not pl or not pl["enabled"] or not pl["penabled"]:
            return tr(lang, "unavailable")
        if stock_count(pl["id"]) == 0:
            return tr(lang, "out_of_stock_alert")
        if a == "pl":
            await show(q, v_checkout(lang, pl))
        elif a == "co":
            await show(q, v_currency(lang, pl))
        elif p[2] not in ("dzd", "usd"):
            return tr(lang, "err_generic")
        elif a == "oc":
            checkout_token = create_wallet_checkout_quote(user["id"], pl["id"], p[2])
            await show(q, v_method(lang, pl, p[2], user["id"], checkout_token))
        else:  # om
            method = p[3]
            if method == "wallet":
                checkout_token = p[4] if len(p) > 4 else None
                status, result = buy_with_wallet(user["id"], pl["id"], p[2], checkout_token)
                if status == "already_processed":
                    return tr(lang, "wallet_duplicate_click")
                if status == "insufficient":
                    return tr(lang, "wallet_insufficient", balance=fmt_cur(result, p[2]))
                if status == "out_of_stock":
                    return tr(lang, "out_of_stock_alert")
                if status != "ok":
                    return tr(lang, "unavailable")
                oid, plan_id = result["order_id"], result["plan_id"]
                await show(q, (tr(lang, "wallet_paid"),
                               Kb([[Btn(tr(lang, "btn_orders"), callback_data="m:orders")],
                                   [Btn(tr(lang, "btn_menu"), callback_data="m:main")]]), None))
                if not await deliver(context.bot, oid):
                    await notify_admins(context.bot, "adm_delivery_failed", markup=Kb([
                        [Btn("🔁 Resend delivery", callback_data=f"A:rd:{oid}")]
                    ]), code=order_code(oid))
                await check_low_stock(context.bot, plan_id)
                return None
            if method not in ("bm", "cr", "binance") or not method_is_enabled(method):
                for key in ("wallet_topup_currency", "wallet_topup_amount_dzd", "wallet_topup_amount_usd"):
                    context.user_data.pop(key, None)
                return tr(lang, "no_methods")
            status, oid = create_order(user["id"], pl["id"], p[2], method)
            if status == "ok":
                await show(q, v_instructions(lang, q1(ORDER_SQL + "WHERE o.id=?", (oid,))))
            elif status == "in_review":
                return tr(lang, "order_in_review")
            elif status == "out_of_stock":
                return tr(lang, "out_of_stock_alert")
            else:
                return tr(lang, "unavailable")
    elif a == "wtm" and len(p) > 1:
        method = p[1]
        amount_dzd = context.user_data.get("wallet_topup_amount_dzd")
        amount_usd = context.user_data.get("wallet_topup_amount_usd")
        currency = context.user_data.get("wallet_topup_currency")
        if method not in ("bm", "cr", "binance") or not method_is_enabled(method):
            for key in ("wallet_topup_currency", "wallet_topup_amount_dzd", "wallet_topup_amount_usd"):
                context.user_data.pop(key, None)
            return tr(lang, "no_methods")
        if not amount_dzd or not amount_usd or currency not in ("dzd", "usd"):
            context.user_data.pop("wallet_topup_amount_dzd", None)
            context.user_data.pop("wallet_topup_amount_usd", None)
            context.user_data.pop("wallet_topup_currency", None)
            return tr(lang, "err_generic")
        topup_id = create_wallet_topup(user["id"], amount_dzd, amount_usd, currency, method)
        context.user_data.pop("wallet_topup_amount_dzd", None)
        context.user_data.pop("wallet_topup_amount_usd", None)
        context.user_data.pop("wallet_topup_currency", None)
        topup = q1("SELECT * FROM wallet_topups WHERE id=? AND user_id=?", (topup_id, user["id"]))
        await show(q, v_wallet_topup_instructions(lang, topup))
    elif a == "wtp" and len(p) > 1:
        topup_id = int(p[1])
        topup = q1("SELECT id,status FROM wallet_topups WHERE id=? AND user_id=?", (topup_id, user["id"]))
        if not topup or topup["status"] != "AWAITING_PROOF":
            return tr(lang, "wallet_topup_not_waiting")
        context.user_data["wallet_topup_proof_id"] = topup_id
        await q.message.chat.send_message(
            tr(lang, "wallet_topup_proof_prompt", code=wallet_topup_code(topup_id)), parse_mode=HTML
        )
    elif a == "wtc" and len(p) > 1:
        topup_id = int(p[1])
        if cancel_wallet_topup(user["id"], topup_id):
            await show(q, (tr(lang, "wallet_topup_cancelled", code=wallet_topup_code(topup_id)),
                           Kb([back_row(lang, "m:wallet")]), None))
        else:
            return tr(lang, "wallet_topup_not_waiting")
    elif a == "ord":
        await show(q, v_order(lang, user, int(p[1])))
    elif a == "cancel":
        oid = int(p[1])
        with tx() as c:
            n = c.execute("UPDATE orders SET status='CANCELLED' WHERE id=? AND user_id=? AND status='AWAITING_PAYMENT'", (oid, user["id"])).rowcount
        if n:
            await show(q, (tr(lang, "order_cancelled", code=order_code(oid)), Kb([[Btn(tr(lang, "btn_menu"), callback_data="m:main")]]), None))
        else:
            return tr(lang, "order_cannot_cancel")
    elif a == "proof":
        oid = int(p[1])
        o = q1("SELECT id,status FROM orders WHERE id=? AND user_id=?", (oid, user["id"]))
        if not o or o["status"] != "AWAITING_PAYMENT":
            return tr(lang, "order_cannot_cancel")
        context.user_data["proof_oid"] = oid
        await q.message.chat.send_message(tr(lang, "send_proof_prompt", code=order_code(oid)), parse_mode=HTML)
    return None


# ════════════════════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ════════════════════════════════════════════════════════════════════════════
def av_home(al):
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_btn_stats"), callback_data="A:stats"), Btn(t("a_btn_products"), callback_data="A:prods")],
             [Btn(t("a_btn_stock"), callback_data="A:stock"), Btn(t("a_btn_payments"), callback_data="A:pay")],
             [Btn(t("a_btn_topups"), callback_data="A:topups")],
             [Btn(t("a_btn_orders"), callback_data="A:ord:all"), Btn(t("a_btn_users"), callback_data="A:users")],
             [Btn(t("a_btn_settings"), callback_data="A:set"), Btn(t("a_btn_broadcast"), callback_data="A:bc")]])
    return tr(al, "a_title"), kb, None


def av_stats(al):
    n = lambda v: f"{int(v):,}"
    pend = "('PENDING','AWAITING_PAYMENT','PAYMENT_REVIEW')"
    d = dict(
        t_orders=n(scalar("SELECT COUNT(*) FROM orders WHERE date(created_at)=date('now')")),
        t_rev=n(scalar("SELECT SUM(amount_dzd) FROM orders WHERE status='COMPLETED' AND date(completed_at)=date('now')")),
        t_users=n(scalar("SELECT COUNT(*) FROM users WHERE date(created_at)=date('now')")),
        t_paid=n(scalar("SELECT COUNT(*) FROM orders WHERE status='COMPLETED' AND date(completed_at)=date('now')")),
        pending_pay=n(scalar("SELECT (SELECT COUNT(*) FROM payments WHERE status='PENDING') + "
                             "(SELECT COUNT(*) FROM wallet_topups WHERE status='PAYMENT_REVIEW')")),
        users=n(scalar("SELECT COUNT(*) FROM users")), orders=n(scalar("SELECT COUNT(*) FROM orders")),
        completed=n(scalar("SELECT COUNT(*) FROM orders WHERE status='COMPLETED'")),
        pending=n(scalar(f"SELECT COUNT(*) FROM orders WHERE status IN {pend}")),
        rejected=n(scalar("SELECT COUNT(*) FROM orders WHERE status='REJECTED'")),
        rev=n(scalar("SELECT SUM(amount_dzd) FROM orders WHERE status='COMPLETED'")),
        avail=n(scalar("SELECT COUNT(*) FROM stock WHERE status='AVAILABLE'")), sold=n(scalar("SELECT COUNT(*) FROM stock WHERE status='SOLD'")))
    return tr(al, "a_stats", **d), Kb([back_row(al, "A:home")]), None


def av_products(al):
    rows = qa("SELECT * FROM products ORDER BY id")
    kb = [[Btn(f"{r['emoji']} {r['name']} {'✅' if r['enabled'] else '🚫'}", callback_data=f"A:p:{r['id']}")] for r in rows]
    kb.append([Btn(tr(al, "a_btn_add_product"), callback_data="A:pn")])
    kb.append(back_row(al, "A:home"))
    return tr(al, "a_prods_title"), Kb(kb), None


def av_product(al, pid):
    p = q1("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return av_products(al)
    plans = qa("SELECT pl.*, (SELECT COUNT(*) FROM stock s WHERE s.plan_id=pl.id AND s.status='AVAILABLE') AS avail FROM plans pl "
               "WHERE product_id=? ORDER BY id", (pid,))
    lines = "\n".join(tr(al, "a_plan_row", name=h(x["name_en"]), ar=h(x["name_ar"]), price=x["price_dzd"], stock=x["avail"],
                         status="✅" if x["enabled"] else "🚫") for x in plans) or "—"
    text = tr(al, "a_product_view", emoji=p["emoji"], name=h(p["name"]), status=tr(al, "a_enabled" if p["enabled"] else "a_disabled"),
              den=h(p["description_en"]) or "—", dar=h(p["description_ar"]) or "—", img="✅" if p["image_file_id"] else "—", plans=lines)
    t = lambda k: tr(al, k)
    kb = [[Btn(t("a_btn_name"), callback_data=f"A:pe:{pid}:name"), Btn(t("a_btn_emoji"), callback_data=f"A:pe:{pid}:emoji")],
          [Btn(t("a_btn_den"), callback_data=f"A:pe:{pid}:description_en"), Btn(t("a_btn_dar"), callback_data=f"A:pe:{pid}:description_ar")],
          [Btn(t("a_btn_image"), callback_data=f"A:pi:{pid}"), Btn(t("a_btn_disable" if p["enabled"] else "a_btn_enable"), callback_data=f"A:pt:{pid}")]]
    kb += [[Btn(f"{x['name_en']} — {x['price_dzd']} DA {'✅' if x['enabled'] else '🚫'}", callback_data=f"A:l:{x['id']}")] for x in plans]
    kb += [[Btn(t("a_btn_add_plan"), callback_data=f"A:ln:{pid}"), Btn(t("a_btn_del_product"), callback_data=f"A:pd:{pid}")], back_row(al, "A:prods")]
    return text, Kb(kb), None


def av_plan(al, plid):
    pl = q1(PLAN_SQL + "WHERE pl.id=?", (plid,))
    if not pl:
        return av_products(al)
    text = tr(al, "a_plan_view", item=item_label(pl, "en"), en=h(pl["name_en"]), ar=h(pl["name_ar"]), price=pl["price_dzd"],
              usd=fmt_usd(to_usd(pl["price_dzd"])), stock=stock_count(plid), status=tr(al, "a_enabled" if pl["enabled"] else "a_disabled"))
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_btn_name_en"), callback_data=f"A:le:{plid}:name_en"), Btn(t("a_btn_name_ar"), callback_data=f"A:le:{plid}:name_ar")],
             [Btn(t("a_btn_price"), callback_data=f"A:le:{plid}:price_dzd"), Btn(t("a_btn_disable" if pl["enabled"] else "a_btn_enable"), callback_data=f"A:lt:{plid}")],
             [Btn(t("a_btn_del_plan"), callback_data=f"A:ld:{plid}")], back_row(al, f"A:p:{pl['product_id']}")])
    return text, kb, None


def stock_lines():
    out = []
    for p in qa("SELECT * FROM products ORDER BY id"):
        out.append(f"<b>{p['emoji']} {h(p['name'])}</b>")
        for pl in qa("SELECT * FROM plans WHERE product_id=? ORDER BY id", (p["id"],)):
            n = stock_count(pl["id"])
            out.append(f"{h(pl['name_en'])} — {'🟢' if n else '🔴'} {n}")
        out.append("")
    return "\n".join(out) or "—"


def av_stock(al):
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_btn_add_stock"), callback_data="A:skpick:add"), Btn(t("a_btn_view_stock"), callback_data="A:skpick:view")],
             [Btn(t("a_btn_rm_stock"), callback_data="A:skpick:rm"), Btn(t("a_btn_stock_stats"), callback_data="A:skstat")], back_row(al, "A:home")])
    return tr(al, "a_stock_title", lines=stock_lines()), kb, None


def av_pick(al, act):
    kb = []
    for pl in qa(PLAN_SQL + "ORDER BY pl.product_id, pl.id"):
        count = stock_count(pl["id"])
        kb.append([Btn(f"{pl['emoji']} {pl['pname']} — {pl['name_en']} ({'🟢' if count else '🔴'} {count})",
                       callback_data=f"A:sk{act}:{pl['id']}")])
    kb.append(back_row(al, "A:stock"))
    return tr(al, "a_pick_plan"), Kb(kb), None


def av_stockview(al, plid):
    pl = q1(PLAN_SQL + "WHERE pl.id=?", (plid,))
    if not pl:
        return av_stock(al)
    cnt = {r["status"]: r["c"] for r in qa("SELECT status, COUNT(*) c FROM stock WHERE plan_id=? GROUP BY status", (plid,))}
    rows = "\n".join(f"#{r['id']} · <code>{h(mask(r['content']))}</code> · {r['added_at'][:10]}" for r in
                     qa("SELECT id,content,added_at FROM stock WHERE plan_id=? AND status='AVAILABLE' ORDER BY id LIMIT 40", (plid,))) or "—"
    text = tr(al, "a_stock_view", item=item_label(pl, "en"), a=cnt.get("AVAILABLE", 0), r=cnt.get("RESERVED", 0), s=cnt.get("SOLD", 0), rows=rows)
    return text, Kb([back_row(al, "A:skpick:view")]), None


def av_stockstats(al):
    out = []
    for pl in qa(PLAN_SQL + "ORDER BY pl.product_id, pl.id"):
        cnt = {r["status"]: r["c"] for r in qa("SELECT status, COUNT(*) c FROM stock WHERE plan_id=? GROUP BY status", (pl["id"],))}
        out.append(f"{item_label(pl, 'en')}\n   🟢 {cnt.get('AVAILABLE', 0)} · 🟡 {cnt.get('RESERVED', 0)} · 🔴 {cnt.get('SOLD', 0)}")
    return tr(al, "a_stock_stats", lines="\n".join(out) or "—"), Kb([back_row(al, "A:stock")]), None


def av_payments(al):
    rows = qa("SELECT pay.id AS pid, o.id AS oid, o.amount_dzd FROM payments pay JOIN orders o ON o.id=pay.order_id "
              "WHERE pay.status='PENDING' ORDER BY pay.id LIMIT 20")
    if not rows:
        return tr(al, "a_pay_none"), Kb([back_row(al, "A:home")]), None
    kb = [[Btn(f"#{order_code(r['oid'])} — {r['amount_dzd']} DA", callback_data=f"A:pv:{r['pid']}")] for r in rows]
    kb.append(back_row(al, "A:home"))
    return tr(al, "a_pay_title", n=len(rows)), Kb(kb), None


def av_topups(al):
    rows = qa(
        "SELECT t.id,t.amount_dzd,t.amount_usd,t.input_currency,t.method,u.first_name,u.username "
        "FROM wallet_topups t JOIN users u ON u.id=t.user_id "
        "WHERE t.status='PAYMENT_REVIEW' ORDER BY t.id LIMIT 20"
    )
    if not rows:
        return tr(al, "a_topups_none"), Kb([back_row(al, "A:home")]), None
    kb = []
    for row in rows:
        amount = fmt_usd(row["amount_usd"]) if row["input_currency"] == "usd" else fmt_dzd(row["amount_dzd"])
        who = row["username"] or row["first_name"] or "customer"
        kb.append([Btn(f"{wallet_topup_code(row['id'])} — {amount} · {who}",
                       callback_data=f"A:tv:{row['id']}")])
    kb.append(back_row(al, "A:home"))
    return tr(al, "a_topups_title", n=len(rows)), Kb(kb), None


def wallet_topup_card(al, topup_id):
    row = q1(
        "SELECT t.*,u.telegram_id AS tg,u.username AS username,u.first_name AS first_name "
        "FROM wallet_topups t JOIN users u ON u.id=t.user_id WHERE t.id=?",
        (topup_id,),
    )
    if not row:
        return None
    amount = f"{fmt_usd(row['amount_usd'])} / {fmt_dzd(row['amount_dzd'])}"
    text = tr(al, "a_topup_card", code=wallet_topup_code(topup_id), customer=customer_str(row),
              amount=amount, method=method_label(al, row["method"]), created=row["created_at"])
    markup = None
    if row["status"] == "PAYMENT_REVIEW":
        markup = Kb([[Btn(tr(al, "a_btn_approve"), callback_data=f"A:tpa:{topup_id}"),
                      Btn(tr(al, "a_btn_reject"), callback_data=f"A:tpr:{topup_id}")]])
    return text, markup, row["proof_file_id"] or ""


async def send_wallet_topup_card(bot, chat_id, al, topup_id):
    card = wallet_topup_card(al, topup_id)
    if not card:
        return
    text, markup, proof = card
    kind, _, fid = proof.partition(":")
    if kind == "photo" and fid:
        await bot.send_photo(chat_id, fid, caption=text, reply_markup=markup, parse_mode=HTML)
    elif kind == "doc" and fid:
        await bot.send_document(chat_id, fid, caption=text, reply_markup=markup, parse_mode=HTML)
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=HTML)


async def notify_admins_wallet_topup(bot, topup_id):
    for aid in ADMIN_IDS:
        try:
            await send_wallet_topup_card(bot, aid, admin_lang(aid), topup_id)
        except TelegramError:
            logger.warning("could not send wallet top-up review to admin %s", aid)


def av_orders(al, pending_only):
    where = "WHERE o.status IN ('PENDING','AWAITING_PAYMENT','PAYMENT_REVIEW') " if pending_only else ""
    rows = qa(ORDER_SQL + where + "ORDER BY o.id DESC LIMIT 15")
    kb = [[Btn(f"#{order_code(o['id'])} {STATUS_EMOJI[o['status']]} {o['pname']}", callback_data=f"A:o:{o['id']}")] for o in rows]
    kb.append([Btn(tr(al, "a_btn_all_orders" if pending_only else "a_btn_only_pending"), callback_data="A:ord:all" if pending_only else "A:ord:p")])
    kb.append(back_row(al, "A:home"))
    return tr(al, "a_orders_title"), Kb(kb), None


def av_order(al, oid):
    o = q1(ORDER_SQL + "WHERE o.id=?", (oid,))
    if not o:
        return av_orders(al, False)
    text = tr(al, "a_order_view", code=order_code(oid), customer=customer_str(o), item=item_label(o, "en"), amount=order_amount(o),
              method=method_label("en", o["payment_method"]), status=tr("en", "st_" + o["status"].lower()), created=o["created_at"],
              completed=o["completed_at"] or "—")
    kb = []
    pay = q1("SELECT id,status FROM payments WHERE order_id=? ORDER BY id DESC LIMIT 1", (oid,))
    if pay and pay["status"] == "PENDING":
        kb.append([Btn(tr(al, "a_btn_review"), callback_data=f"A:pv:{pay['id']}")])
    if o["status"] == "COMPLETED":
        kb.append([Btn(tr(al, "a_btn_resend"), callback_data=f"A:rd:{oid}")])
    kb.append(back_row(al, "A:ord:all"))
    return text, Kb(kb), None


def av_users(al):
    rows = qa("SELECT * FROM users ORDER BY id DESC LIMIT 10")
    kb = [[Btn(tr(al, "a_btn_search"), callback_data="A:us")]]
    kb += [[Btn(f"{'🚫 ' if u['banned'] else ''}{u['first_name'] or '-'} · {('@' + u['username']) if u['username'] else u['telegram_id']}", callback_data=f"A:u:{u['id']}")] for u in rows]
    kb.append(back_row(al, "A:home"))
    return tr(al, "a_users_title"), Kb(kb), None


def av_user(al, uid):
    u = q1("SELECT * FROM users WHERE id=?", (uid,))
    if not u:
        return av_users(al)
    r = q1("SELECT COUNT(*) c, COALESCE(SUM(CASE WHEN status='COMPLETED' THEN amount_dzd END),0) s FROM orders WHERE user_id=?", (uid,))
    text = tr(al, "a_user_view", name=h(u["first_name"] or "-"), tg=u["telegram_id"], username=f"@{h(u['username'])}" if u["username"] else "—",
              date=u["created_at"][:10], orders=r["c"], spent=f"{int(r['s']):,}",
              wallet=fmt_both(wallet_balance_dzd(uid)), banned=tr(al, "a_yes" if u["banned"] else "a_no"))
    kb = Kb([[Btn(tr(al, "a_btn_unban") if u["banned"] else tr(al, "a_btn_ban"), callback_data=f"A:{'uu' if u['banned'] else 'ub'}:{uid}")],
             back_row(al, "A:users")])
    return text, kb, None


CFG = {"usd_rate": "float", "low_stock_threshold": "int", "support_username": "user", "channel": "user",
       "bm_account": "text", "bm_name": "text", "bm_instructions": "text", "bm_qr": "image",
       "cr_currency": "text", "cr_network": "text", "cr_wallet": "text", "cr_instructions": "text",
       "binance_account": "text", "binance_name": "text", "binance_instructions": "text"}


def cfg_val(al, k):
    v = get_setting(k)
    if CFG[k] == "image":
        return tr(al, "a_set") if v else tr(al, "a_unset")
    return h(v) if v else tr(al, "a_unset")


def av_settings(al):
    method_status = lambda method: "ON" if method_is_enabled(method) else ("Not ready" if get_setting(f"{method}_enabled") == "1" else "OFF")
    text = tr(al, "a_settings_title", rate=usd_rate(), thr=h(get_setting("low_stock_threshold")),
              support=("@" + h(get_setting("support_username"))) if get_setting("support_username") else "—",
              channel=("@" + h(get_setting("channel"))) if get_setting("channel") else "—",
              bm=method_status("bm"), cr=method_status("cr"), binance=method_status("binance"))
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_cfg_usd_rate"), callback_data="A:cfg:usd_rate"), Btn(t("a_cfg_low_stock_threshold"), callback_data="A:cfg:low_stock_threshold")],
             [Btn(t("a_btn_bm"), callback_data="A:bm"), Btn(t("a_btn_binance"), callback_data="A:binance")],
             [Btn(t("a_btn_cr"), callback_data="A:cr")],
             [Btn(t("a_cfg_support_username"), callback_data="A:cfg:support_username"), Btn(t("a_cfg_channel"), callback_data="A:cfg:channel")],
             back_row(al, "A:home")])
    return text, kb, None


def av_bm(al):
    enabled = get_setting("bm_enabled") == "1"
    text = tr(al, "a_bm_title", enabled="ON" if enabled else "OFF", account=cfg_val(al, "bm_account"),
              name=cfg_val(al, "bm_name"), instr=cfg_val(al, "bm_instructions"), qr=cfg_val(al, "bm_qr"))
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_cfg_bm_account"), callback_data="A:cfg:bm_account"), Btn(t("a_cfg_bm_name"), callback_data="A:cfg:bm_name")],
             [Btn(t("a_cfg_bm_instructions"), callback_data="A:cfg:bm_instructions")],
             [Btn(t("a_cfg_bm_qr"), callback_data="A:cfgimg:bm_qr"), Btn(t("a_btn_clear_qr"), callback_data="A:cfgclr:bm_qr")],
             [Btn(t("a_btn_disable_method") if enabled else t("a_btn_enable_method"), callback_data="A:toggle:bm")],
             back_row(al, "A:set")])
    return text, kb, None


def av_cr(al):
    enabled = get_setting("cr_enabled") == "1"
    text = tr(al, "a_cr_title", enabled="ON" if enabled else "OFF", network=cfg_val(al, "cr_network"), wallet=cfg_val(al, "cr_wallet"),
              instr=cfg_val(al, "cr_instructions"))
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_cfg_cr_network"), callback_data="A:cfg:cr_network")],
             [Btn(t("a_cfg_cr_wallet"), callback_data="A:cfg:cr_wallet")], [Btn(t("a_cfg_cr_instructions"), callback_data="A:cfg:cr_instructions")],
             [Btn(t("a_btn_disable_method") if enabled else t("a_btn_enable_method"), callback_data="A:toggle:cr")],
             back_row(al, "A:set")])
    return text, kb, None


def av_binance(al):
    configured_enabled = get_setting("binance_enabled") == "1"
    enabled = method_is_enabled("binance")
    status = "ON" if enabled else ("Not ready" if configured_enabled else "OFF")
    text = tr(al, "a_binance_title", account=cfg_val(al, "binance_account"),
              name=cfg_val(al, "binance_name"), instr=cfg_val(al, "binance_instructions"))
    text += f"\n\nStatus: {status}"
    t = lambda k: tr(al, k)
    kb = Kb([[Btn(t("a_cfg_binance_account"), callback_data="A:cfg:binance_account"),
              Btn(t("a_cfg_binance_name"), callback_data="A:cfg:binance_name")],
             [Btn(t("a_cfg_binance_instructions"), callback_data="A:cfg:binance_instructions")],
              [Btn(t("a_btn_disable_method") if configured_enabled else t("a_btn_enable_method"), callback_data="A:toggle:binance")],
             back_row(al, "A:set")])
    return text, kb, None


def cfg_return_view(al, key):
    if key.startswith("bm_"):
        return av_bm(al)
    if key.startswith("cr_"):
        return av_cr(al)
    if key.startswith("binance_"):
        return av_binance(al)
    return av_settings(al)


def validate_cfg(key, text):
    kind, text = CFG[key], text.strip()
    if text == "-" and kind in ("text", "user"):
        return True, ""
    if kind == "float":
        try:
            v = float(text.replace(",", "."))
        except ValueError:
            return False, None
        return (0 < v < 1_000_000), str(v)
    if kind == "int":
        return (text.isdigit() and int(text) <= 1000), text
    if kind == "user":
        u = re.sub(r"^(https?://)?(t\.me/)?@?", "", text)
        return bool(re.fullmatch(r"[A-Za-z0-9_]{3,32}", u)), u
    return (0 < len(text) <= 1000), text


# ════════════════════════════════════════════════════════════════════════════
# ADMIN CALLBACKS
# ════════════════════════════════════════════════════════════════════════════
async def admin_cb(q, context, user, p, st):
    al = lang_of(user)
    T = lambda k, **kw: tr(al, k, **kw)
    a, arg = p[0], p[1:]
    chat = q.message.chat
    ud = context.user_data

    def ask(state, text, back="A:home"):
        ud["st"] = state
        return show(q, (text, Kb([[Btn(T("btn_cancel"), callback_data=back)]]), None))

    if a == "home":
        await show(q, av_home(al))
    elif a == "stats":
        await show(q, av_stats(al))
    elif a == "prods":
        await show(q, av_products(al))
    elif a == "p":
        await show(q, av_product(al, int(arg[0])))
    elif a == "pn":
        await ask({"k": "prod_add"}, T("a_p_prod_add"), "A:prods")
    elif a == "pe" and arg[1] in ("name", "emoji", "description_en", "description_ar"):
        await ask({"k": "prod_edit", "pid": int(arg[0]), "f": arg[1]}, T("a_p_prod_edit", field=arg[1]), f"A:p:{arg[0]}")
    elif a == "pi":
        await ask({"k": "prod_img", "pid": int(arg[0])}, T("a_p_prod_img"), f"A:p:{arg[0]}")
    elif a == "pt":
        ex("UPDATE products SET enabled=1-enabled WHERE id=?", (int(arg[0]),))
        await show(q, av_product(al, int(arg[0])))
    elif a == "pd":
        pr = q1("SELECT name FROM products WHERE id=?", (int(arg[0]),))
        kb = Kb([[Btn(T("a_btn_yes_delete"), callback_data=f"A:pdy:{arg[0]}"), Btn(T("btn_cancel"), callback_data=f"A:p:{arg[0]}")]])
        await show(q, (T("a_confirm_delete", name=h(pr["name"] if pr else "?")), kb, None))
    elif a == "pdy":
        pid = int(arg[0])
        with tx() as c:
            if c.execute("SELECT 1 FROM orders o JOIN plans pl ON pl.id=o.plan_id WHERE pl.product_id=? LIMIT 1", (pid,)).fetchone():
                return T("a_has_orders")
            c.execute("DELETE FROM stock WHERE plan_id IN (SELECT id FROM plans WHERE product_id=?)", (pid,))
            c.execute("DELETE FROM plans WHERE product_id=?", (pid,))
            c.execute("DELETE FROM products WHERE id=?", (pid,))
        await show(q, av_products(al))
        return T("a_deleted")
    elif a == "l":
        await show(q, av_plan(al, int(arg[0])))
    elif a == "ln":
        await ask({"k": "plan_add", "pid": int(arg[0])}, T("a_p_plan_add"), f"A:p:{arg[0]}")
    elif a == "le" and arg[1] in ("name_en", "name_ar", "price_dzd"):
        await ask({"k": "plan_edit", "plid": int(arg[0]), "f": arg[1]}, T("a_p_plan_edit", field=arg[1]), f"A:l:{arg[0]}")
    elif a == "lt":
        ex("UPDATE plans SET enabled=1-enabled WHERE id=?", (int(arg[0]),))
        await show(q, av_plan(al, int(arg[0])))
    elif a == "ld":
        pl = q1(PLAN_SQL + "WHERE pl.id=?", (int(arg[0]),))
        kb = Kb([[Btn(T("a_btn_yes_delete"), callback_data=f"A:ldy:{arg[0]}"), Btn(T("btn_cancel"), callback_data=f"A:l:{arg[0]}")]])
        await show(q, (T("a_confirm_delete", name=item_label(pl, "en") if pl else "?"), kb, None))
    elif a == "ldy":
        plid = int(arg[0])
        pl = q1("SELECT product_id FROM plans WHERE id=?", (plid,))
        with tx() as c:
            if c.execute("SELECT 1 FROM orders WHERE plan_id=? LIMIT 1", (plid,)).fetchone():
                return T("a_has_orders")
            c.execute("DELETE FROM stock WHERE plan_id=?", (plid,))
            c.execute("DELETE FROM plans WHERE id=?", (plid,))
        await show(q, av_product(al, pl["product_id"]) if pl else av_products(al))
        return T("a_deleted")
    # ── stock ──
    elif a == "stock":
        await show(q, av_stock(al))
    elif a == "skpick" and arg[0] in ("add", "view", "rm"):
        await show(q, av_pick(al, arg[0]))
    elif a == "skadd":
        pl = q1(PLAN_SQL + "WHERE pl.id=?", (int(arg[0]),))
        await ask({"k": "stock_add", "plid": int(arg[0])}, T("a_p_stock_add", item=item_label(pl, "en")), "A:stock")
    elif a == "skview":
        await show(q, av_stockview(al, int(arg[0])))
    elif a == "skrm":
        pl = q1(PLAN_SQL + "WHERE pl.id=?", (int(arg[0]),))
        await ask({"k": "stock_rm", "plid": int(arg[0])}, T("a_p_stock_rm", item=item_label(pl, "en")), "A:stock")
    elif a == "skstat":
        await show(q, av_stockstats(al))
    # ── payments ──
    elif a == "pay":
        await show(q, av_payments(al))
    elif a == "topups":
        await show(q, av_topups(al))
    elif a == "tv":
        await send_wallet_topup_card(context.bot, chat.id, al, int(arg[0]))
    elif a == "tpa":
        topup_id = int(arg[0])
        result = approve_wallet_topup(topup_id)
        if not result:
            return T("a_err_topup_done")
        await edit_card(q, "\n\n" + T("a_topup_approved"))
        lang = result["language"] if result["language"] in LANGS else "en"
        try:
            await context.bot.send_message(
                result["telegram_id"],
                tr(lang, "wallet_credit_notice", code=wallet_topup_code(topup_id),
                   amount=fmt_both(result["amount_dzd"]),
                   balance=fmt_both(result["balance_dzd"])),
                parse_mode=HTML,
            )
        except TelegramError:
            logger.warning("could not notify customer about wallet top-up %s", topup_id)
    elif a == "tpr":
        topup_id = int(arg[0])
        if scalar("SELECT COUNT(*) FROM wallet_topups WHERE id=? AND status='PAYMENT_REVIEW'", (topup_id,)) == 0:
            return T("a_err_topup_done")
        ud["st"] = {"k": "topup_reject", "topup_id": topup_id}
        await chat.send_message(
            T("a_p_reject"),
            reply_markup=Kb([[Btn(T("a_btn_skip"), callback_data=f"A:tprs:{topup_id}")]]),
        )
    elif a == "tprs":
        if not await do_reject_wallet_topup(context.bot, int(arg[0]), ""):
            return T("a_err_topup_done")
        await edit_card(q, "\n\n" + T("a_topup_rejected"))
    elif a == "pv":
        await send_payment_card(context.bot, chat.id, al, int(arg[0]))
    elif a == "pa":
        pid = int(arg[0])
        code, d = approve_payment(pid)
        if code != "ok":
            return T({"done": "a_err_done", "bad_order": "a_err_bad_order", "banned": "a_err_banned", "no_stock": "a_err_no_stock"}[code])
        await edit_card(q, "\n\n" + T("a_approved"))
        if not await deliver(context.bot, d["order_id"]):
            kb = Kb([[Btn(T("a_btn_resend"), callback_data=f"A:rd:{d['order_id']}")]])
            await notify_admins(context.bot, "adm_delivery_failed", markup=kb, code=order_code(d["order_id"]))
        await check_low_stock(context.bot, d["plan_id"])
    elif a == "pr":
        pid = int(arg[0])
        if scalar("SELECT COUNT(*) FROM payments WHERE id=? AND status='PENDING'", (pid,)) == 0:
            return T("a_err_done")
        ud["st"] = {"k": "reject", "pid": pid}
        await chat.send_message(T("a_p_reject"), reply_markup=Kb([[Btn(T("a_btn_skip"), callback_data=f"A:prs:{pid}")]]))
    elif a == "prs":
        res = await do_reject(context.bot, int(arg[0]), "")
        if not res:
            return T("a_err_done")
        await q.message.edit_text(T("a_rejected"))
    elif a == "rd":
        ok = await deliver(context.bot, int(arg[0]))
        return T("a_resent") if ok else T("err_generic")
    # ── orders ──
    elif a == "ord":
        await show(q, av_orders(al, arg[0] == "p"))
    elif a == "o":
        await show(q, av_order(al, int(arg[0])))
    # ── users ──
    elif a == "users":
        await show(q, av_users(al))
    elif a == "us":
        await ask({"k": "user_search"}, T("a_p_search"), "A:users")
    elif a == "u":
        await show(q, av_user(al, int(arg[0])))
    elif a in ("ub", "uu"):
        ex("UPDATE users SET banned=? WHERE id=?", (1 if a == "ub" else 0, int(arg[0])))
        await show(q, av_user(al, int(arg[0])))
    # ── broadcast ──
    elif a == "bc":
        await ask({"k": "bc"}, T("a_p_bc"))
    elif a == "bcy":
        if not st or st.get("k") != "bcconfirm":
            return T("a_err_done")
        users = [r["telegram_id"] for r in qa("SELECT telegram_id FROM users WHERE banned=0")]
        await q.message.edit_text(T("a_bc_started", n=len(users)))
        context.application.create_task(run_broadcast(context.bot, chat.id, st["chat"], st["mid"], users, al))
    # ── settings ──
    elif a == "set":
        await show(q, av_settings(al))
    elif a == "bm":
        await show(q, av_bm(al))
    elif a == "cr":
        await show(q, av_cr(al))
    elif a == "binance":
        await show(q, av_binance(al))
    elif a == "toggle" and arg[0] in ("bm", "cr", "binance"):
        method = arg[0]
        ready = {
            "bm": bool(get_setting("bm_account")),
            "cr": bool(get_setting("cr_wallet") and get_setting("cr_network")),
            "binance": bool(get_setting("binance_account")),
        }[method]
        if get_setting(f"{method}_enabled") != "1" and not ready:
            return T("a_method_not_ready")
        set_setting(f"{method}_enabled", "0" if get_setting(f"{method}_enabled") == "1" else "1")
        await show(q, {"bm": av_bm, "cr": av_cr, "binance": av_binance}[method](al))
    elif a == "cfg" and arg[0] in CFG and CFG[arg[0]] != "image":
        hint = {"float": "\nExample: <code>255</code>", "int": "\nExample: <code>3</code>", "user": "\nExample: <code>@my_support</code>"}.get(CFG[arg[0]], "")
        await ask({"k": "cfg", "key": arg[0]}, T("a_p_cfg", label=T("a_cfg_" + arg[0]), hint=hint), "A:set")
    elif a == "cfgimg" and arg[0] in CFG and CFG[arg[0]] == "image":
        await ask({"k": "cfgimg", "key": arg[0]}, T("a_p_cfgimg", label=T("a_cfg_" + arg[0])), "A:bm")
    elif a == "cfgclr" and arg[0] == "bm_qr":
        set_setting("bm_qr", "")
        await show(q, av_bm(al))
    return None


async def edit_card(q, suffix):
    msg = q.message
    try:
        if msg.caption is not None:
            await msg.edit_caption(caption=msg.caption_html + suffix, parse_mode=HTML, reply_markup=None)
        else:
            await msg.edit_text(msg.text_html + suffix, parse_mode=HTML, reply_markup=None)
    except TelegramError:
        pass


async def do_reject(bot, pid, note):
    oid = reject_payment(pid, note)
    if not oid:
        return False
    o = q1(ORDER_SQL + "WHERE o.id=?", (oid,))
    lang = o["ulang"] if o["ulang"] in LANGS else "en"
    reason = tr(lang, "reason_line", reason=h(note)) + "\n" if note else ""
    try:
        await bot.send_message(o["tg"], tr(lang, "payment_rejected", code=order_code(oid), reason=reason), parse_mode=HTML)
    except TelegramError:
        logger.warning("could not notify user about rejected order %s", oid)
    return True


async def do_reject_wallet_topup(bot, topup_id, note):
    result = reject_wallet_topup(topup_id, note)
    if not result:
        return False
    lang = result["language"] if result["language"] in LANGS else "en"
    reason = tr(lang, "topup_reject_reason", reason=h(note)) + "\n" if note else ""
    try:
        await bot.send_message(
            result["telegram_id"],
            tr(lang, "wallet_rejected_notice", code=wallet_topup_code(topup_id), reason=reason),
            parse_mode=HTML,
        )
    except TelegramError:
        logger.warning("could not notify customer about rejected wallet top-up %s", topup_id)
    return True


async def run_broadcast(bot, admin_chat, from_chat, mid, users, al):
    ok = fail = 0
    for tg in users:
        for _ in range(2):
            try:
                await bot.copy_message(chat_id=tg, from_chat_id=from_chat, message_id=mid)
                ok += 1
                break
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except (Forbidden, BadRequest):
                fail += 1
                break
            except TelegramError:
                fail += 1
                break
        await asyncio.sleep(BROADCAST_DELAY)
    try:
        await bot.send_message(admin_chat, tr(al, "a_bc_done", ok=ok, fail=fail))
    except TelegramError:
        pass


# ════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ════════════════════════════════════════════════════════════════════════════
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    tg = q.from_user
    user = cached_user(tg, context)
    lang = lang_of(user)
    if user["banned"] and not is_admin(tg.id):
        await q.answer(tr(lang, "banned"), show_alert=True)
        return
    p = (q.data or "").split(":")
    alert = None
    try:
        if p[0] == "A":
            if not is_admin(tg.id):
                await q.answer()
                return
            st = context.user_data.pop("st", None)  # pressing any admin button cancels a pending text prompt
            alert = await admin_cb(q, context, user, p[1:], st)
        else:
            alert = await user_cb(q, context, user, p)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning("BadRequest in callback: %s", e)
    except (ValueError, IndexError, KeyError):
        logger.warning("invalid callback data: %r", q.data)
        alert = tr(lang, "err_generic")
    except Exception:
        logger.exception("callback error")
        alert = tr(lang, "err_generic")
    try:
        await q.answer(alert, show_alert=bool(alert))
    except TelegramError:
        pass


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg, chat = update.effective_user, update.effective_chat
    user = cached_user(tg, context, refresh=True)
    context.user_data.pop("st", None)
    if user["banned"] and not is_admin(tg.id):
        await chat.send_message(tr(lang_of(user), "banned"))
    elif user["language"] not in LANGS:
        await send_view(chat, v_lang_choice())
    else:
        await send_view(chat, v_main(user["language"]))


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg = update.effective_user
    if not is_admin(tg.id):
        return
    user = cached_user(tg, context, refresh=True)
    context.user_data.pop("st", None)
    await send_view(update.effective_chat, av_home(lang_of(user)))


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = cached_user(update.effective_user, context, refresh=True)
    context.user_data.pop("st", None)
    context.user_data.pop("proof_oid", None)
    for key in ("wallet_topup_currency", "wallet_topup_amount_dzd", "wallet_topup_amount_usd",
                "wallet_topup_proof_id"):
        context.user_data.pop(key, None)
    await update.effective_chat.send_message(tr(lang_of(user), "a_cancelled"))


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg, tg = update.effective_message, update.effective_user
    if not msg or not tg:
        return
    user = cached_user(tg, context, refresh=True)
    lang = lang_of(user)
    admin = is_admin(tg.id)
    if user["banned"] and not admin:
        await msg.reply_text(tr(lang, "banned"))
        return
    st = context.user_data.get("st") if admin else None
    if st:
        await admin_input(update, context, user, st)
        return
    if context.user_data.get("wallet_topup_currency") and msg.text:
        await handle_wallet_topup_amount(update, context, user)
        return
    if user["language"] not in LANGS:
        await send_view(msg.chat, v_lang_choice())
        return
    if msg.photo or msg.document:
        await handle_proof(update, context, user)
        return
    await send_view(msg.chat, v_main(lang))


async def handle_proof(update, context, user):
    msg, lang = update.effective_message, lang_of(user)
    topup_id = context.user_data.get("wallet_topup_proof_id")
    if topup_id:
        topup = q1(
            "SELECT id FROM wallet_topups WHERE id=? AND user_id=? AND status='AWAITING_PROOF'",
            (topup_id, user["id"]),
        )
        if not topup:
            context.user_data.pop("wallet_topup_proof_id", None)
            await msg.reply_text(tr(lang, "wallet_topup_not_waiting"))
            return
        proof = f"photo:{msg.photo[-1].file_id}" if msg.photo else f"doc:{msg.document.file_id}"
        if not submit_wallet_topup_proof(user["id"], topup_id, proof):
            await msg.reply_text(tr(lang, "wallet_topup_not_waiting"))
            return
        context.user_data.pop("wallet_topup_proof_id", None)
        await msg.reply_text(
            tr(lang, "wallet_topup_received", code=wallet_topup_code(topup_id)),
            parse_mode=HTML,
            reply_markup=Kb([[Btn(tr(lang, "btn_wallet"), callback_data="m:wallet")]]),
        )
        await notify_admins_wallet_topup(context.bot, topup_id)
        return
    oid = context.user_data.get("proof_oid")
    o = q1("SELECT id FROM orders WHERE id=? AND user_id=? AND status='AWAITING_PAYMENT'", (oid, user["id"])) if oid else None
    if not o:  # fall back to the latest order that is waiting for payment
        o = q1("SELECT id FROM orders WHERE user_id=? AND status='AWAITING_PAYMENT' ORDER BY id DESC LIMIT 1", (user["id"],))
    if not o:
        await msg.reply_text(tr(lang, "no_pending_order"))
        return
    proof = f"photo:{msg.photo[-1].file_id}" if msg.photo else f"doc:{msg.document.file_id}"
    pid = submit_proof(user["id"], o["id"], proof)
    if not pid:
        await msg.reply_text(tr(lang, "no_pending_order"))
        return
    context.user_data.pop("proof_oid", None)
    await msg.reply_text(tr(lang, "proof_received", code=order_code(o["id"])), parse_mode=HTML,
                         reply_markup=Kb([[Btn(tr(lang, "btn_menu"), callback_data="m:main")]]))
    await notify_admins_payment(context.bot, pid)


async def handle_wallet_topup_amount(update, context, user):
    msg, lang = update.effective_message, lang_of(user)
    currency = context.user_data.get("wallet_topup_currency")
    if not available_funding_methods():
        for key in ("wallet_topup_currency", "wallet_topup_amount_dzd", "wallet_topup_amount_usd"):
            context.user_data.pop(key, None)
        await msg.reply_text(tr(lang, "wallet_no_funding_methods"))
        return
    amount_dzd, amount_usd, error = parse_wallet_topup_amount(msg.text, currency)
    if error:
        minimum = (fmt_usd((Decimal(100) / Decimal(str(usd_rate()))).quantize(Decimal("0.01"), rounding=ROUND_CEILING))
                   if currency == "usd" else fmt_dzd(100))
        maximum = (fmt_usd((Decimal(25_000_000) / Decimal(str(usd_rate()))).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))
                   if currency == "usd" else fmt_dzd(25_000_000))
        kwargs = {"minimum": minimum} if error == "wallet_amount_small" else (
            {"maximum": maximum} if error == "wallet_amount_large" else {})
        await msg.reply_text(tr(lang, error, **kwargs))
        return
    context.user_data["wallet_topup_amount_dzd"] = amount_dzd
    context.user_data["wallet_topup_amount_usd"] = amount_usd
    await send_view(msg.chat, v_wallet_funding_methods(lang, amount_dzd, amount_usd, currency))


async def admin_input(update, context, user, st):
    msg, al = update.effective_message, lang_of(user)
    T = lambda k, **kw: tr(al, k, **kw)
    chat, k = msg.chat, st["k"]
    text = (msg.text or "").strip()
    ud = context.user_data

    async def bad():
        await msg.reply_text(T("a_bad_input"))

    async def done(view, note=None):
        ud.pop("st", None)
        if note:
            await chat.send_message(note, parse_mode=HTML)
        await send_view(chat, view)

    if k == "topup_reject":
        if not text or len(text) > 300:
            return await bad()
        ud.pop("st", None)
        ok = await do_reject_wallet_topup(context.bot, st["topup_id"], text)
        await chat.send_message(T("a_topup_rejected") if ok else T("a_err_topup_done"))
    elif k == "prod_add":
        parts = [x.strip() for x in text.split("|")]
        if len(parts) < 2 or not parts[1] or len(parts[1]) > 64:
            return await bad()
        parts += [""] * (4 - len(parts))
        pid = ex("INSERT INTO products(emoji,name,description_en,description_ar) VALUES(?,?,?,?)", (parts[0][:8] or "🛍️", parts[1], parts[2][:600], parts[3][:600]))
        await done(av_product(al, pid), T("a_saved"))
    elif k == "prod_edit":
        limit = {"name": 64, "emoji": 8}.get(st["f"], 600)
        if not text or len(text) > limit:
            return await bad()
        ex(f"UPDATE products SET {st['f']}=? WHERE id=?", (text, st["pid"]))  # column name is whitelisted in admin_cb
        await done(av_product(al, st["pid"]), T("a_saved"))
    elif k == "prod_img":
        if not msg.photo:
            return await bad()
        ex("UPDATE products SET image_file_id=? WHERE id=?", (msg.photo[-1].file_id, st["pid"]))
        await done(av_product(al, st["pid"]), T("a_saved"))
    elif k == "plan_add":
        parts = [x.strip() for x in text.split("|")]
        if len(parts) != 3 or not parts[0] or not parts[1] or not parts[2].isdigit() or int(parts[2]) <= 0:
            return await bad()
        ex("INSERT INTO plans(product_id,name_en,name_ar,price_dzd) VALUES(?,?,?,?)", (st["pid"], parts[0][:64], parts[1][:64], int(parts[2])))
        await done(av_product(al, st["pid"]), T("a_saved"))
    elif k == "plan_edit":
        if st["f"] == "price_dzd":
            if not text.isdigit() or int(text) <= 0:
                return await bad()
            val = int(text)
        else:
            if not text or len(text) > 64:
                return await bad()
            val = text
        ex(f"UPDATE plans SET {st['f']}=? WHERE id=?", (val, st["plid"]))
        await done(av_plan(al, st["plid"]), T("a_saved"))
    elif k == "stock_add":
        raw = text
        doc = msg.document
        if doc and (doc.file_name or "").lower().endswith(".txt") and (doc.file_size or 0) < 1_000_000:
            raw = bytes(await (await doc.get_file()).download_as_bytearray()).decode("utf-8", "ignore")
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if not lines or len(lines) > 5000 or any(len(ln) > 2000 for ln in lines):
            return await bad()
        added, dup = add_stock(st["plid"], lines)
        try:
            await msg.delete()  # don't leave credentials lying in the chat
        except TelegramError:
            pass
        await done(av_stock(al), T("a_stock_added", n=added, dup=T("a_stock_dups", d=dup) if dup else ""))
    elif k == "stock_rm":
        with tx() as c:
            if text.lower() == "all":
                n = c.execute("DELETE FROM stock WHERE plan_id=? AND status='AVAILABLE'", (st["plid"],)).rowcount
            else:
                ids = [int(x) for x in re.findall(r"\d+", text)][:500]
                if not ids:
                    return await bad()
                n = c.execute(f"DELETE FROM stock WHERE plan_id=? AND status='AVAILABLE' AND id IN ({','.join('?' * len(ids))})", (st["plid"], *ids)).rowcount
        await done(av_stock(al), T("a_stock_removed", n=n))
        await check_low_stock(context.bot, st["plid"])
    elif k == "cfg":
        ok, val = validate_cfg(st["key"], text)
        if not ok:
            return await bad()
        set_setting(st["key"], val)
        method_for_key = {"bm_account": "bm", "cr_wallet": "cr", "cr_network": "cr",
                          "binance_account": "binance"}.get(st["key"])
        if method_for_key and not val:
            set_setting(f"{method_for_key}_enabled", "0")
        await done(cfg_return_view(al, st["key"]), T("a_saved"))
    elif k == "cfgimg":
        if not msg.photo:
            return await bad()
        set_setting(st["key"], msg.photo[-1].file_id)
        await done(cfg_return_view(al, st["key"]), T("a_saved"))
    elif k == "reject":
        if not text or len(text) > 300:
            return await bad()
        ud.pop("st", None)
        ok = await do_reject(context.bot, st["pid"], text)
        await chat.send_message(T("a_rejected") if ok else T("a_err_done"))
    elif k in ("bc", "bcconfirm"):
        ud["st"] = {"k": "bcconfirm", "chat": chat.id, "mid": msg.message_id}
        await chat.send_message(T("a_bc_confirm"), reply_markup=Kb([[Btn(T("a_btn_confirm"), callback_data="A:bcy"), Btn(T("btn_cancel"), callback_data="A:home")]]),
                                reply_to_message_id=msg.message_id)
    elif k == "user_search":
        if not text:
            return await bad()
        like = "%" + text.lstrip("@").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = qa("SELECT * FROM users WHERE telegram_id=? OR username LIKE ? ESCAPE '\\' OR first_name LIKE ? ESCAPE '\\' LIMIT 10",
                  (int(text) if text.isdigit() else -1, like, like))
        ud.pop("st", None)
        if not rows:
            await chat.send_message(T("a_no_results"))
            return
        kb = [[Btn(f"{'🚫 ' if u['banned'] else ''}{u['first_name'] or '-'} · {('@' + u['username']) if u['username'] else u['telegram_id']}", callback_data=f"A:u:{u['id']}")] for u in rows]
        kb.append(back_row(al, "A:users"))
        await chat.send_message(T("a_users_title"), reply_markup=Kb(kb), parse_mode=HTML)


async def on_error(update, context):
    logger.error("Unhandled error: %s", type(context.error).__name__, exc_info=context.error)


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable is missing.\n  Windows: set BOT_TOKEN=YOUR_TOKEN\n  Linux/macOS: export BOT_TOKEN=YOUR_TOKEN")
    init_db()
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS is empty – nobody can use /admin. Example: set ADMIN_IDS=123456789,987654321")
    app = (Application.builder()
           .token(BOT_TOKEN)
           .connection_pool_size(32)
           .pool_timeout(5)
           .connect_timeout(10)
           .read_timeout(20)
           .write_timeout(20)
           .build())
    private = filters.ChatType.PRIVATE
    app.add_handler(CommandHandler("start", cmd_start, filters=private))
    app.add_handler(CommandHandler("admin", cmd_admin, filters=private))
    app.add_handler(CommandHandler("cancel", cmd_cancel, filters=private))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(private & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    logger.info("Subzy Store is running…")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
