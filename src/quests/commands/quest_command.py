from typing import Any

from endstone.command import Command, CommandSender

from quests.managers import QuestManager


class QuestCommand:
    def __init__(self, manager: QuestManager):
        self.manager = manager

    def handle(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        name = command.name.lower()
        if name in ["quests", "quest"]:
            return self.handle_quests(sender, args)
        if name in ["questadmin", "qadmin"]:
            return self.handle_admin(sender, args)
        return False

    def handle_quests(self, sender: CommandSender, args: list[str]) -> bool:
        if not args:
            if self.manager.is_player(sender):
                self.manager.open_quest_menu(sender)
            else:
                self.manager.send_player_help(sender)
            return True

        if args[0].lower() == "help":
            self.manager.send_player_help(sender)
            return True

        subcommand = args[0].lower()

        if subcommand in ["menu", "gui", "open"]:
            if not self.manager.is_player(sender):
                self.manager.send(sender, "error.players_only")
                return True
            self.manager.open_quest_menu(sender)
            return True

        if subcommand == "list":
            self.manager.send_quest_list(sender)
            return True

        if subcommand == "info":
            if len(args) < 2:
                self.manager.send(sender, "error.usage", usage="/quests info <quest>")
                return True
            self.manager.send_quest_info(sender, args[1])
            return True

        if subcommand == "start":
            if len(args) < 2:
                self.manager.send(sender, "error.usage", usage="/quests start <quest>")
                return True
            if not self.manager.is_player(sender):
                self.manager.send(sender, "error.players_only")
                return True
            self.manager.start_quest(sender, args[1])
            return True

        if subcommand in ["progress", "status"]:
            if not self.manager.is_player(sender):
                self.manager.send(sender, "error.players_only")
                return True
            self.manager.send_progress(sender, args[1] if len(args) >= 2 else None)
            return True

        if subcommand == "cancel":
            if len(args) < 2:
                self.manager.send(sender, "error.usage", usage="/quests cancel <quest>")
                return True
            if not self.manager.is_player(sender):
                self.manager.send(sender, "error.players_only")
                return True
            self.manager.cancel_quest(sender, args[1])
            return True

        self.manager.send(sender, "error.unknown_command")
        return True

    def handle_admin(self, sender: CommandSender, args: list[str]) -> bool:
        if not sender.has_permission("quests.admin"):
            self.manager.send(sender, "error.no_permission")
            return True

        if not args or args[0].lower() == "help":
            self.manager.send_admin_help(sender)
            return True

        subcommand = args[0].lower()

        if subcommand == "reload":
            self.manager.reload_all()
            self.manager.send(sender, "admin.reload")
            return True

        if subcommand == "list":
            self.manager.send_quest_list(sender)
            self.manager.send_raw(sender, f"&7Objective types: &f{self.manager.admin_objective_types()}", prefixed=True)
            return True

        if subcommand in ["progress", "addprogress", "add"]:
            if len(args) < 4:
                self.manager.send(sender, "error.usage", usage="/questadmin progress <player> <type> <amount> [target]")
                return True

            target_player = self.manager.find_player(args[1])
            if target_player is None:
                self.manager.send(sender, "error.player_missing", player=args[1])
                return True

            objective_type = self.manager.normalize_objective_type(args[2])
            if objective_type is None:
                self.manager.send(sender, "error.invalid_type", type=args[2])
                return True

            amount = self.parse_amount(sender, args[3])
            if amount is None:
                return True

            target = args[4] if len(args) >= 5 else None
            self.manager.progress_objective(target_player, objective_type, amount, target)
            self.manager.send(
                sender,
                "admin.progress",
                player=target_player.name,
                type=objective_type,
                amount=self.manager.display_number(amount),
            )
            return True

        if subcommand == "reset":
            if len(args) < 2:
                self.manager.send(sender, "error.usage", usage="/questadmin reset <player> [quest]")
                return True

            target_player = self.manager.find_player(args[1])
            if target_player is None:
                self.manager.send(sender, "error.player_missing", player=args[1])
                return True

            self.manager.reset_player(target_player, args[2] if len(args) >= 3 else None)
            self.manager.send(sender, "admin.reset", player=target_player.name)
            return True

        if subcommand == "complete":
            if len(args) < 3:
                self.manager.send(sender, "error.usage", usage="/questadmin complete <player> <quest>")
                return True

            target_player = self.manager.find_player(args[1])
            if target_player is None:
                self.manager.send(sender, "error.player_missing", player=args[1])
                return True

            if not self.manager.force_complete(target_player, args[2]):
                self.manager.send(sender, "error.quest_missing", quest=args[2])
                return True

            self.manager.send(sender, "admin.complete", player=target_player.name, quest=args[2])
            return True

        self.manager.send(sender, "error.unknown_command")
        return True

    def parse_amount(self, sender: Any, value: str) -> float | None:
        try:
            amount = float(value)
        except Exception:
            self.manager.send(sender, "error.invalid_amount")
            return None

        if amount <= 0:
            self.manager.send(sender, "error.invalid_amount")
            return None

        return amount
