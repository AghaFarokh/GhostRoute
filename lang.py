STRINGS = {
    "fa": {
        # ── Panel ──────────────────────────────────────────────────
        "panel_header":   "ربات چرخش تتر USDT در شبکه BSC",
        "hops":           "چرخه",
        "hops_btn":       "چرخه",
        "fee":            "کارمزد",
        "expiry":         "انقضا",
        "min":            "دقیقه",
        "wallet_label":   "کیف پول مقصد",
        "wallet_not_set": "تنظیم نشده",
        "status_label":   "وضعیت",
        "status_idle":    "آماده",

        # ── Buttons ────────────────────────────────────────────────
        "btn_wallet_set":   "✅ کیف پول",
        "btn_wallet_unset": "❌ کیف پول",
        "btn_start":        "🚀 شروع",
        "btn_history":      "📜 تاریخچه",
        "btn_cancel_all":   "❌ لغو همه",
        "btn_admin":        "🔑 پنل مدیر",
        "btn_info":         "ℹ️ راهنما",
        "btn_lang":         "🌐 English",
        "btn_cancel_cycle": "❌ لغو",
        "btn_extend":       "⏰ +۱ ساعت",
        "btn_relaunch":     "🔄 راه‌اندازی مجدد",
        "btn_time_minus":   "⏱️ -۳۰ دقیقه",
        "btn_time_plus":    "⏱️ +۳۰ دقیقه",
        "time_unit":        " دقیقه",

        # ── Wallet FSM ─────────────────────────────────────────────
        "send_wallet":          "آدرس کیف پول مقصد خود را ارسال کنید:",
        "invalid_address":      "❌ آدرس نامعتبر است",
        "contract_not_allowed": "❌ آدرس قراردادها مجاز نیست",
        "wallet_saved":         "✅ کیف پول ذخیره شد",

        # ── Cycle start / waiting ──────────────────────────────────
        "set_wallet_first": "ابتدا کیف پول مقصد را تنظیم کنید",
        "expires_label":    "⏰ انقضا:",
        "waiting_deposit":  (
            "⏳ منتظر واریز به کیف پول چرخه اول هستیم.\n"
            "برای تمدید یا لغو از دکمه‌های زیر استفاده کنید."
        ),

        # ── History ────────────────────────────────────────────────
        "history_title": "📜 تاریخچه (۵ مورد اخیر)\n\n",
        "no_cycles":     "چرخه‌ای یافت نشد.",
        "status_col":    "وضعیت",
        "hops_col":      "چرخه‌ها",
        "dest_col":      "مقصد",
        "created_col":   "تاریخ",

        # ── Alerts ────────────────────────────────────────────────
        "all_cancelled":         "همه چرخه‌های فعال لغو شدند",
        "cycle_cancelled_alert": "چرخه لغو شد",
        "already_done":          "چرخه قبلاً تکمیل یا لغو شده است",
        "cycle_not_found":       "چرخه یافت نشد",
        "invalid_cycle":         "شناسه چرخه نامعتبر است",
        "extended_alert":        "تمدید شد! انقضای جدید: ",
        "cannot_extend":         "این چرخه قابل تمدید نیست",
        "started_alert":         "شروع شد",
        "restarted_alert":       "راه‌اندازی مجدد شد",
        "already_running":       "در حال اجرا است",
        "only_expired":          "فقط چرخه‌های منقضی",

        # ── Info ──────────────────────────────────────────────────
        "info_text": (
            "ℹ️ *ربات چرخش تتر USDT در شبکه BSC*\n\n"
            "این ربات تراکنش‌های USDT شما را از طریق چندین کیف پول میانی "
            "در شبکه BSC منتقل می‌دهد تا ردیابی آن دشوارتر شود.\n\n"
            "🔄 *نحوه کار:*\n"
            "۱. تعداد چرخه را انتخاب کنید (حداقل ۲، حداکثر ۱۰)\n"
            "۲. زمان انقضا را تنظیم کنید\n"
            "۳. کیف پول مقصد را وارد کنید\n"
            "۴. چرخه را شروع کنید\n"
            "۵. USDT را به آدرس نمایش‌داده‌شده ارسال کنید\n"
            "۶. ربات به‌صورت خودکار مبلغ را از طریق چرخه‌های میانی تا مقصد منتقل می‌کند\n\n"
            "💰 *کارمزد:*\n"
            "به ازای هر چرخه ۰.۵ USDT کارمزد دریافت می‌شود.\n\n"
            "🔐 *امنیت کلیدهای خصوصی:*\n"
            "• در ابتدای هر تراکنش، کلیدهای خصوصی کیف پول‌های میانی برای شما ارسال می‌شود\n"
            "• این کلیدها را در مکانی امن ذخیره کنید\n"
            "• در صورت بروز مشکل می‌توانید با آن‌ها دارایی خود را بازیابی کنید\n"
            "• ربات برای هر تراکنش کیف پول‌های جدید و کاملاً منحصربه‌فرد می‌سازد\n\n"
            "⚠️ *هشدار امنیتی:*\n"
            "امنیت دارایی شما تا زمانی تضمین است که کد منبع این ربات "
            "در اختیار دیگران نباشد. هرگز کلیدهای خصوصی یا اطلاعات ربات "
            "را با کسی به اشتراک نگذارید."
        ),
    },

    "en": {
        # ── Panel ──────────────────────────────────────────────────
        "panel_header":   "USDT HOP BOT",
        "hops":           "Hops",
        "hops_btn":       "HOPS",
        "fee":            "Fee",
        "expiry":         "Expiry",
        "min":            "min",
        "wallet_label":   "Wallet",
        "wallet_not_set": "Not Set",
        "status_label":   "Status",
        "status_idle":    "Idle",

        # ── Buttons ────────────────────────────────────────────────
        "btn_wallet_set":   "✅ Wallet",
        "btn_wallet_unset": "❌ Wallet",
        "btn_start":        "🚀 Start",
        "btn_history":      "📜 History",
        "btn_cancel_all":   "❌ Cancel All",
        "btn_admin":        "🔑 Admin Panel",
        "btn_info":         "ℹ️ Info",
        "btn_lang":         "🌐 فارسی",
        "btn_cancel_cycle": "❌ Cancel",
        "btn_extend":       "⏰ +1hr",
        "btn_relaunch":     "🔄 Relaunch",
        "btn_time_minus":   "⏱️ -30m",
        "btn_time_plus":    "⏱️ +30m",
        "time_unit":        "m",

        # ── Wallet FSM ─────────────────────────────────────────────
        "send_wallet":          "Send your final destination wallet address:",
        "invalid_address":      "❌ Invalid address",
        "contract_not_allowed": "❌ Contract addresses not allowed",
        "wallet_saved":         "✅ Wallet saved",

        # ── Cycle start / waiting ──────────────────────────────────
        "set_wallet_first": "Set wallet first",
        "expires_label":    "⏰ Expires:",
        "waiting_deposit":  (
            "⏳ Waiting for deposit to hop 1 wallet.\n"
            "Tap Extend to add 1 hour, or Cancel to abort."
        ),

        # ── History ────────────────────────────────────────────────
        "history_title": "📜 HISTORY (last 5)\n\n",
        "no_cycles":     "No cycles yet.",
        "status_col":    "Status",
        "hops_col":      "Hops",
        "dest_col":      "Destination",
        "created_col":   "Created",

        # ── Alerts ────────────────────────────────────────────────
        "all_cancelled":         "All active cycles cancelled",
        "cycle_cancelled_alert": "Cycle cancelled",
        "already_done":          "Cycle already completed or cancelled",
        "cycle_not_found":       "Cycle not found",
        "invalid_cycle":         "Invalid cycle",
        "extended_alert":        "Extended! New expiry: ",
        "cannot_extend":         "Cannot extend this cycle",
        "started_alert":         "Started",
        "restarted_alert":       "Restarted",
        "already_running":       "Already running",
        "only_expired":          "Only expired cycles",

        # ── Info ──────────────────────────────────────────────────
        "info_text": (
            "ℹ️ *About USDT Hop Bot*\n\n"
            "This bot routes your USDT through multiple intermediate wallets "
            "on the BSC network, making transactions harder to trace.\n\n"
            "🔄 *How it works:*\n"
            "1. Choose the number of hops (min 2, max 10)\n"
            "2. Set the expiry time\n"
            "3. Set your destination wallet\n"
            "4. Start the cycle\n"
            "5. Send USDT to the hop 1 address shown\n"
            "6. The bot automatically routes funds through each hop "
            "to your destination\n\n"
            "💰 *Fee:*\n"
            "0.5 USDT per hop is charged as the service fee.\n\n"
            "🔐 *Private Key Safety:*\n"
            "• At the start of every cycle, private keys for all hop wallets "
            "are sent to you\n"
            "• Store them somewhere safe\n"
            "• You can use them to manually recover funds if anything goes wrong\n"
            "• The bot generates brand new unique wallets for every single cycle\n\n"
            "⚠️ *Security Warning:*\n"
            "Your funds are safe as long as the source code of this bot is not "
            "accessible to others. Never share your private keys or bot details "
            "with anyone."
        ),
    },
}


def get(user_id, key, user_setups_dict):
    lang = user_setups_dict.get(user_id, {}).get("lang", "fa")
    bucket = STRINGS.get(lang, STRINGS["fa"])
    return bucket.get(key, STRINGS["en"].get(key, key))
