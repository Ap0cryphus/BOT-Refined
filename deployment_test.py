"""Manual live preflight for the UI-Automation build."""

from camfrog_bot import CamfrogBot


def main() -> int:
    bot = CamfrogBot(dry_run=True)
    if not bot.initialize():
        print(bot.ui_automation.last_error)
        return 1
    print("Connected through Windows UI Automation.")
    print("Live UIA locations:", bot.ui_automation.layout_locations())
    print("Visible roster users:", bot.ui_automation.get_user_list())
    print("Visible chat events:", bot.ui_automation.get_chat_events())
    print("Dry-run mode: no messages will be sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
