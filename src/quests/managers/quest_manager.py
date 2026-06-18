import math
import time
from pathlib import Path
from typing import Any

from endstone.form import ActionForm
from endstone.inventory import ItemStack

from quests.constants import (
    COLOR,
    EVENT_OBJECTIVE_TYPES,
    OBJECTIVE_ALIASES,
    OBJECTIVE_TYPES,
    default_config,
    default_quests,
)
from quests.storage import JsonStorage


class QuestManager:
    def __init__(self, plugin: Any):
        self.plugin = plugin
        self.server = plugin.server
        self.logger = plugin.logger
        self.data_folder = Path(plugin.data_folder)
        self.data_folder.mkdir(parents=True, exist_ok=True)

        self.config_path = self.data_folder / "config.json"
        self.quests_path = self.data_folder / "quests.json"
        self.players_path = self.data_folder / "players.json"
        self.storage = JsonStorage(self.logger)
        self.progress_message_cooldowns: dict[str, float] = {}

        self.reload_all()

    def reload_all(self):
        self.config = self.storage.load_dict_with_defaults(self.config_path, default_config())
        legacy_quests = self.cleanup_legacy_config()
        if not self.quests_path.exists() and self.should_migrate_legacy_quests(legacy_quests):
            self.storage.save_dict(self.quests_path, {"schema_version": 1, "quests": legacy_quests})
        self.quests_data = self.storage.load_dict_with_defaults(self.quests_path, default_quests())
        self.players = self.storage.load_dict_with_defaults(
            self.players_path,
            {"schema_version": 1, "players": {}},
        )

    def cleanup_legacy_config(self) -> dict[str, Any] | None:
        legacy_quests = self.config.get("quests")
        removed = False
        for key in ("objective_types", "quests"):
            if key in self.config:
                self.config.pop(key, None)
                removed = True

        if removed:
            self.storage.save_dict(self.config_path, self.config)

        return legacy_quests if isinstance(legacy_quests, dict) else None

    def should_migrate_legacy_quests(self, legacy_quests: dict[str, Any] | None) -> bool:
        if not legacy_quests:
            return False

        legacy_keys = {str(key) for key in legacy_quests}
        return legacy_keys != {"starter", "all_types_template"}

    def save_players(self):
        self.storage.save_dict(self.players_path, self.players)

    def format_text(self, text: Any, **kwargs: Any) -> str:
        value = str(text)
        try:
            value = value.format(**kwargs)
        except Exception:
            pass

        return value.replace("&", COLOR)

    def send(self, sender: Any, message_key: str, prefixed: bool = True, **kwargs: Any):
        messages = self.config.get("messages", {})
        text = messages.get(message_key, message_key)
        prefix = self.config.get("settings", {}).get("prefix", "")

        message = self.format_text(text, **kwargs)
        if prefixed:
            message = self.format_text(prefix, **kwargs) + message

        sender.send_message(message)

    def send_raw(self, sender: Any, text: str, prefixed: bool = False, **kwargs: Any):
        prefix = self.config.get("settings", {}).get("prefix", "")
        message = self.format_text(text, **kwargs)
        if prefixed:
            message = self.format_text(prefix, **kwargs) + message
        sender.send_message(message)

    def is_player(self, sender: Any) -> bool:
        return (
            hasattr(sender, "name")
            and hasattr(sender, "unique_id")
            and hasattr(sender, "location")
            and hasattr(sender, "send_message")
        )

    def player_key(self, player: Any) -> str:
        try:
            return str(player.unique_id)
        except Exception:
            return str(getattr(player, "name", "unknown")).lower()

    def player_record(self, player: Any) -> dict[str, Any]:
        players = self.players.setdefault("players", {})
        record = players.setdefault(
            self.player_key(player),
            {"name": getattr(player, "name", "unknown"), "active": {}, "completed": {}},
        )
        record["name"] = getattr(player, "name", record.get("name", "unknown"))
        record.setdefault("active", {})
        record.setdefault("completed", {})
        return record

    def find_player(self, name: str) -> Any | None:
        try:
            player = self.server.get_player(name)
            if player is not None:
                return player
        except Exception:
            pass

        requested = name.lower()
        for player in self.server.online_players:
            if str(player.name).lower() == requested:
                return player

        return None

    def normalize_objective_type(self, objective_type: Any) -> str | None:
        value = str(objective_type).strip().lower().replace("-", "_").replace(" ", "_")
        value = OBJECTIVE_ALIASES.get(value, value)
        return value if value in OBJECTIVE_TYPES else None

    def normalize_id(self, value: Any) -> str:
        normalized = str(value).strip().lower()
        if not normalized or normalized == "*":
            return "*"
        if ":" not in normalized and not normalized.startswith("#"):
            normalized = f"minecraft:{normalized}"
        return normalized

    def display_number(self, value: Any) -> str:
        try:
            number = float(value)
        except Exception:
            return str(value)

        if number.is_integer():
            return str(int(number))
        return f"{number:.1f}".rstrip("0").rstrip(".")

    def objective_amount(self, objective: dict[str, Any]) -> float:
        try:
            return max(0.0, float(objective.get("amount", 1)))
        except Exception:
            return 1.0

    def objective_id(self, objective: dict[str, Any], index: int) -> str:
        if "id" in objective:
            return str(objective["id"])
        objective_type = self.normalize_objective_type(objective.get("type", "")) or "objective"
        return f"{objective_type}_{index}"

    def objective_description(self, objective: dict[str, Any]) -> str:
        if "description" in objective:
            return self.format_text(objective["description"])

        objective_type = self.normalize_objective_type(objective.get("type", "")) or str(objective.get("type", "goal"))
        target = objective.get("target") or objective.get("targets") or "anything"
        amount = self.display_number(self.objective_amount(objective))
        return f"{objective_type.replace('_', ' ').title()} {amount} {target}"

    def quest_name(self, quest_id: str, quest: dict[str, Any] | None = None) -> str:
        quest = self.get_quest(quest_id) if quest is None else quest
        if quest is None:
            return quest_id
        return self.format_text(quest.get("display_name", quest_id))

    def quests(self) -> dict[str, Any]:
        quests = self.quests_data.get("quests", {})
        return quests if isinstance(quests, dict) else {}

    def get_quest(self, quest_id: str) -> dict[str, Any] | None:
        requested = quest_id.strip().lower()
        for current_id, quest in self.quests().items():
            if str(current_id).lower() == requested and isinstance(quest, dict):
                return quest
        return None

    def match_quest_id(self, quest_id: str) -> str | None:
        requested = quest_id.strip().lower()
        for current_id, quest in self.quests().items():
            if str(current_id).lower() == requested and isinstance(quest, dict):
                return str(current_id)
        return None

    def enabled_quests(self) -> dict[str, dict[str, Any]]:
        return {
            str(quest_id): quest
            for quest_id, quest in self.quests().items()
            if isinstance(quest, dict) and bool(quest.get("enabled", True))
        }

    def quest_objectives(self, quest: dict[str, Any]) -> list[dict[str, Any]]:
        objectives = quest.get("objectives", [])
        return [objective for objective in objectives if isinstance(objective, dict)]

    def start_auto_quests(self, player: Any):
        if not bool(self.config.get("settings", {}).get("auto_start_enabled", True)):
            return

        for quest_id, quest in self.enabled_quests().items():
            if bool(quest.get("auto_start", False)):
                self.start_quest(player, quest_id, quiet=True, auto=True)

    def start_quest(self, player: Any, quest_id: str, quiet: bool = False, auto: bool = False) -> bool:
        matched_id = self.match_quest_id(quest_id)
        if matched_id is None:
            if not quiet:
                self.send(player, "error.quest_missing", quest=quest_id)
            return False

        quest = self.get_quest(matched_id)
        if quest is None:
            if not quiet:
                self.send(player, "error.quest_missing", quest=quest_id)
            return False

        if not bool(quest.get("enabled", True)):
            if not quiet:
                self.send(player, "error.quest_disabled", quest=matched_id)
            return False

        record = self.player_record(player)
        active = record.setdefault("active", {})
        completed = record.setdefault("completed", {})

        if matched_id in active:
            if not quiet:
                self.send(player, "error.quest_active", name=self.quest_name(matched_id, quest))
            return False

        repeatable = bool(quest.get("repeatable", False))
        if not repeatable and matched_id in completed:
            if not quiet:
                self.send(player, "error.quest_completed", name=self.quest_name(matched_id, quest))
            return False

        active[matched_id] = {
            "started_at": int(time.time()),
            "objectives": {
                self.objective_id(objective, index): 0.0
                for index, objective in enumerate(self.quest_objectives(quest))
            },
        }
        self.save_players()

        if not quiet:
            self.send(player, "quest.started", name=self.quest_name(matched_id, quest))
        elif auto:
            self.send(player, "quest.auto_started", name=self.quest_name(matched_id, quest))
        return True

    def cancel_quest(self, player: Any, quest_id: str):
        matched_id = self.match_quest_id(quest_id)
        if matched_id is None:
            self.send(player, "error.quest_missing", quest=quest_id)
            return

        quest = self.get_quest(matched_id) or {}
        record = self.player_record(player)
        active = record.setdefault("active", {})
        if matched_id not in active:
            self.send(player, "error.quest_not_active", name=self.quest_name(matched_id, quest))
            return

        active.pop(matched_id, None)
        self.save_players()
        self.send(player, "quest.cancelled", name=self.quest_name(matched_id, quest))

    def reset_player(self, player: Any, quest_id: str | None = None):
        record = self.player_record(player)
        if quest_id is None:
            record["active"] = {}
            record["completed"] = {}
        else:
            matched_id = self.match_quest_id(quest_id) or quest_id
            record.setdefault("active", {}).pop(matched_id, None)
            record.setdefault("completed", {}).pop(matched_id, None)
        self.save_players()

    def force_complete(self, player: Any, quest_id: str) -> bool:
        matched_id = self.match_quest_id(quest_id)
        if matched_id is None:
            return False

        quest = self.get_quest(matched_id)
        if quest is None:
            return False

        record = self.player_record(player)
        active = record.setdefault("active", {})
        active.setdefault(matched_id, {"started_at": int(time.time()), "objectives": {}})
        for index, objective in enumerate(self.quest_objectives(quest)):
            active[matched_id].setdefault("objectives", {})[self.objective_id(objective, index)] = self.objective_amount(objective)
        self.complete_quest(player, matched_id, quest)
        return True

    def progress_objective(
        self,
        player: Any,
        objective_type: str,
        amount: float = 1.0,
        target: Any | None = None,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        normalized_type = self.normalize_objective_type(objective_type)
        if normalized_type is None:
            return False

        if amount <= 0:
            return False

        self.start_auto_quests(player)
        record = self.player_record(player)
        active = record.setdefault("active", {})
        if not active:
            return False

        changed = False
        completed_quests: list[tuple[str, dict[str, Any]]] = []
        meta = meta or {}

        for quest_id, quest_state in list(active.items()):
            quest = self.get_quest(quest_id)
            if quest is None or not bool(quest.get("enabled", True)):
                continue

            objective_progress = quest_state.setdefault("objectives", {})
            objective_completed = False

            for index, objective in enumerate(self.quest_objectives(quest)):
                objective_id = self.objective_id(objective, index)
                configured_type = self.normalize_objective_type(objective.get("type", ""))
                if configured_type != normalized_type:
                    continue
                if not self.objective_matches(objective, target, meta):
                    continue

                needed = self.objective_amount(objective)
                current = float(objective_progress.get(objective_id, 0.0))
                if current >= needed:
                    continue

                new_value = min(needed, current + amount)
                objective_progress[objective_id] = new_value
                changed = True

                if new_value >= needed and current < needed:
                    objective_completed = True
                    self.notify_objective_complete(player, objective)
                else:
                    self.notify_progress(player, quest_id, objective_id, quest, objective, new_value, needed)

            if objective_completed and self.is_quest_complete(quest, quest_state):
                completed_quests.append((quest_id, quest))

        for quest_id, quest in completed_quests:
            self.complete_quest(player, quest_id, quest)

        if changed:
            self.save_players()

        return changed

    def objective_matches(self, objective: dict[str, Any], target: Any | None, meta: dict[str, Any]) -> bool:
        configured_targets = objective.get("targets", objective.get("target"))
        if configured_targets is None or configured_targets == "" or configured_targets == "*":
            return True

        if not isinstance(configured_targets, list):
            configured_targets = [configured_targets]

        actual_values = []
        if target is not None:
            actual_values.append(target)
        for key in ("source", "result", "victim_name", "damage_type"):
            if key in meta and meta[key] is not None:
                actual_values.append(meta[key])

        normalized_actual = {self.normalize_id(value) for value in actual_values}
        raw_actual = {str(value).strip().lower() for value in actual_values}

        for configured_target in configured_targets:
            normalized_target = self.normalize_id(configured_target)
            if normalized_target == "*":
                return True
            if normalized_target in normalized_actual or str(configured_target).strip().lower() in raw_actual:
                return True

        return False

    def is_quest_complete(self, quest: dict[str, Any], quest_state: dict[str, Any]) -> bool:
        objective_progress = quest_state.setdefault("objectives", {})
        objectives = self.quest_objectives(quest)
        if not objectives:
            return True

        for index, objective in enumerate(objectives):
            objective_id = self.objective_id(objective, index)
            if float(objective_progress.get(objective_id, 0.0)) < self.objective_amount(objective):
                return False
        return True

    def complete_quest(self, player: Any, quest_id: str, quest: dict[str, Any]):
        record = self.player_record(player)
        active = record.setdefault("active", {})
        active.pop(quest_id, None)

        completed = record.setdefault("completed", {})
        previous = completed.get(quest_id, {})
        completed[quest_id] = {
            "completed_at": int(time.time()),
            "times_completed": int(previous.get("times_completed", 0)) + 1,
        }

        self.apply_rewards(player, quest_id, quest)
        self.send(player, "quest.complete", name=self.quest_name(quest_id, quest))
        self.save_players()

    def notify_objective_complete(self, player: Any, objective: dict[str, Any]):
        if not bool(self.config.get("settings", {}).get("show_objective_complete_messages", True)):
            return

        self.send(
            player,
            "quest.objective_complete",
            description=self.objective_description(objective),
        )

    def notify_progress(
        self,
        player: Any,
        quest_id: str,
        objective_id: str,
        quest: dict[str, Any],
        objective: dict[str, Any],
        progress: float,
        amount: float,
    ):
        if not bool(self.config.get("settings", {}).get("show_progress_messages", False)):
            return

        cooldown_seconds = max(0.0, float(self.config.get("settings", {}).get("progress_message_min_interval_seconds", 3)))
        cooldown_key = f"{self.player_key(player)}:{quest_id}:{objective_id}"
        now = time.time()
        if self.progress_message_cooldowns.get(cooldown_key, 0.0) > now:
            return

        self.progress_message_cooldowns[cooldown_key] = now + cooldown_seconds
        self.send(
            player,
            "quest.progress",
            name=self.quest_name(quest_id, quest),
            description=self.objective_description(objective),
            progress=self.display_number(progress),
            amount=self.display_number(amount),
        )

    def apply_rewards(self, player: Any, quest_id: str, quest: dict[str, Any]):
        rewards = quest.get("rewards", {})
        if not isinstance(rewards, dict):
            return

        for item_config in rewards.get("items", []) or []:
            if not isinstance(item_config, dict):
                continue
            try:
                self.give_item(player, self.create_item(item_config))
            except Exception as error:
                self.logger.error(f"Could not give quest reward item for {quest_id}: {error}")

        exp = int(rewards.get("exp", 0) or 0)
        if exp > 0:
            player.give_exp(exp)

        exp_levels = int(rewards.get("exp_levels", 0) or 0)
        if exp_levels > 0:
            player.give_exp_levels(exp_levels)

        for command in rewards.get("commands", []) or []:
            command_line = str(command).format(player=player.name, quest=quest_id)
            try:
                self.server.dispatch_command(self.server.command_sender, command_line)
            except Exception as error:
                self.logger.error(f"Could not run quest reward command '{command_line}': {error}")

        for command in rewards.get("player_commands", []) or []:
            command_line = str(command).format(player=player.name, quest=quest_id)
            try:
                player.perform_command(command_line)
            except Exception as error:
                self.logger.error(f"Could not run quest player reward command '{command_line}': {error}")

        for message in rewards.get("messages", []) or []:
            self.send_raw(player, str(message), prefixed=True, player=player.name, quest=quest_id)

        for message in rewards.get("broadcasts", []) or []:
            self.server.broadcast_message(
                self.format_text(str(message), player=player.name, quest=self.quest_name(quest_id, quest))
            )

    def create_item(self, item_config: dict[str, Any]) -> ItemStack:
        item_type = self.normalize_id(item_config.get("type", "minecraft:stone"))
        amount = max(1, int(item_config.get("amount", 1) or 1))
        item = ItemStack(item_type, amount)

        meta = item.item_meta
        if "name" in item_config:
            meta.display_name = self.format_text(item_config["name"])
        if isinstance(item_config.get("lore"), list):
            meta.lore = [self.format_text(line) for line in item_config["lore"]]
        item.set_item_meta(meta)
        return item

    def give_item(self, player: Any, item: ItemStack):
        leftovers = player.inventory.add_item(item)
        for leftover in leftovers.values():
            try:
                player.location.dimension.drop_item(player.location, leftover)
            except Exception as error:
                self.logger.warning(f"Could not drop leftover quest reward: {error}")

    def block_type_id(self, block: Any) -> str:
        try:
            return self.normalize_id(block.type)
        except Exception:
            return ""

    def item_type_id(self, item: Any) -> str:
        if item is None:
            return ""

        try:
            item_type = item.type
            return self.normalize_id(getattr(item_type, "id", item_type))
        except Exception:
            return ""

    def actor_type_id(self, actor: Any) -> str:
        try:
            return self.normalize_id(actor.type)
        except Exception:
            return ""

    def is_player_actor(self, actor: Any) -> bool:
        return hasattr(actor, "unique_id") and hasattr(actor, "xuid")

    def source_player(self, damage_source: Any) -> Any | None:
        for attr in ("actor", "damaging_actor"):
            try:
                actor = getattr(damage_source, attr)
            except Exception:
                actor = None
            if actor is not None and self.is_player_actor(actor):
                return actor
        return None

    def distance_between(self, from_location: Any, to_location: Any) -> float:
        try:
            dx = float(to_location.x) - float(from_location.x)
            dy = float(to_location.y) - float(from_location.y)
            dz = float(to_location.z) - float(from_location.z)
        except Exception:
            return 0.0

        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def send_player_help(self, sender: Any):
        self.send(sender, "quest.help.header", prefixed=False)
        self.send(sender, "quest.help.menu", prefixed=False)
        self.send(sender, "quest.help.list", prefixed=False)
        self.send(sender, "quest.help.start", prefixed=False)
        self.send(sender, "quest.help.progress", prefixed=False)
        self.send(sender, "quest.help.info", prefixed=False)
        self.send(sender, "quest.help.cancel", prefixed=False)

    def send_admin_help(self, sender: Any):
        self.send(sender, "admin.help.header", prefixed=False)
        self.send(sender, "admin.help.reload", prefixed=False)
        self.send(sender, "admin.help.list", prefixed=False)
        self.send(sender, "admin.help.progress", prefixed=False)
        self.send(sender, "admin.help.reset", prefixed=False)
        self.send(sender, "admin.help.complete", prefixed=False)

    def send_quest_list(self, sender: Any):
        quests = self.enabled_quests()
        if not quests:
            self.send(sender, "quest.list.none")
            return

        record = self.player_record(sender) if self.is_player(sender) else {}
        active = record.get("active", {})
        completed = record.get("completed", {})

        self.send(sender, "quest.list.header", prefixed=False)
        for quest_id, quest in quests.items():
            if quest_id in active:
                status = "active"
            elif quest_id in completed:
                status = "completed"
            else:
                status = "available"
            self.send(
                sender,
                "quest.list.entry",
                prefixed=False,
                id=quest_id,
                name=self.quest_name(quest_id, quest),
                status=status,
            )

    def send_quest_info(self, sender: Any, quest_id: str):
        matched_id = self.match_quest_id(quest_id)
        if matched_id is None:
            self.send(sender, "error.quest_missing", quest=quest_id)
            return

        quest = self.get_quest(matched_id) or {}
        self.send(sender, "quest.info.header", prefixed=False, name=self.quest_name(matched_id, quest))
        self.send(sender, "quest.info.description", prefixed=False, description=quest.get("description", ""))
        for objective in self.quest_objectives(quest):
            self.send(
                sender,
                "quest.info.objective",
                prefixed=False,
                description=self.objective_description(objective),
                amount=self.display_number(self.objective_amount(objective)),
            )

    def send_progress(self, player: Any, quest_id: str | None = None):
        record = self.player_record(player)
        active = record.setdefault("active", {})
        if not active:
            self.send(player, "quest.progress.none")
            return

        quest_ids = [self.match_quest_id(quest_id) or quest_id] if quest_id else list(active.keys())
        for active_quest_id in quest_ids:
            if active_quest_id not in active:
                quest = self.get_quest(active_quest_id) or {}
                self.send(player, "error.quest_not_active", name=self.quest_name(active_quest_id, quest))
                continue

            quest = self.get_quest(active_quest_id)
            if quest is None:
                continue

            self.send(player, "quest.progress.header", prefixed=False, name=self.quest_name(active_quest_id, quest))
            objective_progress = active[active_quest_id].setdefault("objectives", {})
            for index, objective in enumerate(self.quest_objectives(quest)):
                objective_id = self.objective_id(objective, index)
                progress = float(objective_progress.get(objective_id, 0.0))
                amount = self.objective_amount(objective)
                self.send(
                    player,
                    "quest.progress.objective",
                    prefixed=False,
                    description=self.objective_description(objective),
                    progress=self.display_number(min(progress, amount)),
                    amount=self.display_number(amount),
                )

    def admin_objective_types(self) -> str:
        event_types = ", ".join(sorted(EVENT_OBJECTIVE_TYPES))
        manual_types = ", ".join(sorted(set(OBJECTIVE_TYPES) - EVENT_OBJECTIVE_TYPES))
        return f"event: {event_types}; manual/future-api: {manual_types}"

    def menu_text(self, message_key: str, fallback: str, **kwargs: Any) -> str:
        messages = self.config.get("messages", {})
        return self.format_text(messages.get(message_key, fallback), **kwargs)

    def open_quest_menu(self, player: Any):
        if not self.is_player(player):
            self.send(player, "error.players_only")
            return

        quests = self.enabled_quests()
        record = self.player_record(player)
        active = record.setdefault("active", {})
        completed = record.setdefault("completed", {})

        active_count = sum(1 for quest_id in quests if quest_id in active)
        completed_count = sum(1 for quest_id in quests if quest_id in completed)
        available_count = sum(1 for quest_id in quests if self.quest_status(player, quest_id) == "available")

        form = ActionForm(
            title=self.menu_text("quest.menu.title", "&d&lQuests"),
            content=self.menu_text(
                "quest.menu.content",
                "&7Active: &f{active} &8| &7Available: &f{available} &8| &7Completed: &f{completed}",
                active=active_count,
                available=available_count,
                completed=completed_count,
            ),
        )
        form.add_button(
            self.menu_text("quest.menu.all", "&fAll Quests"),
            on_click=lambda clicked_player: self.open_quest_list_menu(clicked_player, "all"),
        )
        form.add_button(
            self.menu_text("quest.menu.active", "&eActive Quests"),
            on_click=lambda clicked_player: self.open_quest_list_menu(clicked_player, "active"),
        )
        form.add_button(
            self.menu_text("quest.menu.available", "&bAvailable Quests"),
            on_click=lambda clicked_player: self.open_quest_list_menu(clicked_player, "available"),
        )
        form.add_button(
            self.menu_text("quest.menu.completed", "&aCompleted Quests"),
            on_click=lambda clicked_player: self.open_quest_list_menu(clicked_player, "completed"),
        )
        player.send_form(form)

    def open_quest_list_menu(self, player: Any, status_filter: str = "all"):
        quests = self.enabled_quests()
        filtered_quests: list[tuple[str, dict[str, Any]]] = []
        for quest_id, quest in quests.items():
            status = self.quest_status(player, quest_id)
            if status_filter == "all" or status_filter == status:
                filtered_quests.append((quest_id, quest))

        title = self.menu_text(f"quest.menu.{status_filter}.title", "&d&lQuests")
        form = ActionForm(title=title, content=self.menu_text("quest.menu.select", "&7Select a quest to view details."))

        if not filtered_quests:
            form.add_label(self.menu_text("quest.menu.no_quests", "&7No quests in this view."))

        for quest_id, quest in filtered_quests:
            form.add_button(
                self.quest_menu_button(player, quest_id, quest),
                on_click=lambda clicked_player, selected_id=quest_id: self.open_quest_detail_menu(
                    clicked_player,
                    selected_id,
                    status_filter,
                ),
            )

        form.add_button(
            self.menu_text("quest.menu.back", "&8Back"),
            on_click=lambda clicked_player: self.open_quest_menu(clicked_player),
        )
        player.send_form(form)

    def open_quest_detail_menu(self, player: Any, quest_id: str, return_filter: str = "all"):
        matched_id = self.match_quest_id(quest_id)
        if matched_id is None:
            self.send(player, "error.quest_missing", quest=quest_id)
            self.open_quest_list_menu(player, return_filter)
            return

        quest = self.get_quest(matched_id) or {}
        status = self.quest_status(player, matched_id)
        status_label = self.quest_status_label(status)
        content_lines = [
            self.format_text(quest.get("description", "")),
            "",
            self.menu_text("quest.menu.detail.status", "&7Status: &f{status}", status=status_label),
            "",
            self.menu_text("quest.menu.detail.objectives", "&dObjectives"),
            *self.quest_objective_lines(player, matched_id, quest),
        ]

        reward_lines = self.quest_reward_lines(quest)
        if reward_lines:
            content_lines.extend(["", self.menu_text("quest.menu.detail.rewards", "&dRewards"), *reward_lines])

        form = ActionForm(
            title=self.quest_name(matched_id, quest),
            content="\n".join(line for line in content_lines if line is not None),
        )

        if self.can_start_quest(player, matched_id, quest):
            form.add_button(
                self.menu_text("quest.menu.start", "&aStart Quest"),
                on_click=lambda clicked_player: self.start_quest_from_menu(clicked_player, matched_id, return_filter),
            )

        if status == "active":
            form.add_button(
                self.menu_text("quest.menu.cancel", "&cCancel Quest"),
                on_click=lambda clicked_player: self.cancel_quest_from_menu(clicked_player, matched_id, return_filter),
            )

        form.add_button(
            self.menu_text("quest.menu.back", "&8Back"),
            on_click=lambda clicked_player: self.open_quest_list_menu(clicked_player, return_filter),
        )
        player.send_form(form)

    def start_quest_from_menu(self, player: Any, quest_id: str, return_filter: str):
        self.start_quest(player, quest_id)
        self.open_quest_detail_menu(player, quest_id, return_filter)

    def cancel_quest_from_menu(self, player: Any, quest_id: str, return_filter: str):
        self.cancel_quest(player, quest_id)
        self.open_quest_detail_menu(player, quest_id, return_filter)

    def quest_status(self, player: Any, quest_id: str) -> str:
        record = self.player_record(player)
        if quest_id in record.setdefault("active", {}):
            return "active"
        if quest_id in record.setdefault("completed", {}):
            return "completed"
        return "available"

    def quest_status_label(self, status: str) -> str:
        labels = {
            "active": self.menu_text("quest.menu.status.active", "&eActive"),
            "completed": self.menu_text("quest.menu.status.completed", "&aCompleted"),
            "available": self.menu_text("quest.menu.status.available", "&bAvailable"),
        }
        return labels.get(status, status.title())

    def quest_menu_button(self, player: Any, quest_id: str, quest: dict[str, Any]) -> str:
        return self.menu_text(
            "quest.menu.quest_button",
            "{status}: {name}\n{summary}",
            status=self.quest_status_label(self.quest_status(player, quest_id)),
            name=self.quest_name(quest_id, quest),
            summary=self.quest_summary(player, quest_id, quest),
        )

    def quest_summary(self, player: Any, quest_id: str, quest: dict[str, Any]) -> str:
        status = self.quest_status(player, quest_id)
        objectives = self.quest_objectives(quest)
        if not objectives:
            return self.menu_text("quest.menu.summary.no_objectives", "&7No objectives")

        if status == "completed":
            completed = self.player_record(player).setdefault("completed", {}).get(quest_id, {})
            times = int(completed.get("times_completed", 1) or 1)
            return self.menu_text("quest.menu.summary.completed", "&7Completed {times}x", times=times)

        progress = self.quest_progress_values(player, quest_id, quest)
        completed_count = sum(1 for current, needed in progress if current >= needed)
        total = len(progress)
        percent = int(round((completed_count / total) * 100)) if total else 100
        if status == "active":
            return self.menu_text(
                "quest.menu.summary.active",
                "&7{completed}/{total} objectives ({percent}%)",
                completed=completed_count,
                total=total,
                percent=percent,
            )
        return self.menu_text("quest.menu.summary.available", "&7Not started")

    def quest_progress_values(self, player: Any, quest_id: str, quest: dict[str, Any]) -> list[tuple[float, float]]:
        record = self.player_record(player)
        status = self.quest_status(player, quest_id)
        active_state = record.setdefault("active", {}).get(quest_id, {})
        objective_progress = active_state.setdefault("objectives", {}) if isinstance(active_state, dict) else {}

        values = []
        for index, objective in enumerate(self.quest_objectives(quest)):
            needed = self.objective_amount(objective)
            if status == "completed":
                current = needed
            elif status == "active":
                current = float(objective_progress.get(self.objective_id(objective, index), 0.0))
            else:
                current = 0.0
            values.append((min(current, needed), needed))
        return values

    def quest_objective_lines(self, player: Any, quest_id: str, quest: dict[str, Any]) -> list[str]:
        lines = []
        progress_values = self.quest_progress_values(player, quest_id, quest)
        for index, objective in enumerate(self.quest_objectives(quest)):
            current, needed = progress_values[index]
            lines.append(
                self.menu_text(
                    "quest.menu.objective",
                    "&7- &f{description} &8(&d{progress}&7/&d{amount}&8)",
                    description=self.objective_description(objective),
                    progress=self.display_number(current),
                    amount=self.display_number(needed),
                )
            )
        return lines or [self.menu_text("quest.menu.no_objectives", "&7No objectives.")]

    def quest_reward_lines(self, quest: dict[str, Any]) -> list[str]:
        rewards = quest.get("rewards", {})
        if not isinstance(rewards, dict):
            return []

        lines = []
        for item_config in rewards.get("items", []) or []:
            if not isinstance(item_config, dict):
                continue
            amount = max(1, int(item_config.get("amount", 1) or 1))
            item_name = item_config.get("name") or str(item_config.get("type", "minecraft:stone"))
            lines.append(
                self.menu_text(
                    "quest.menu.reward.item",
                    "&7- &f{amount}x {item}",
                    amount=amount,
                    item=self.format_text(item_name),
                )
            )

        exp = int(rewards.get("exp", 0) or 0)
        if exp > 0:
            lines.append(self.menu_text("quest.menu.reward.exp", "&7- &f{exp} XP", exp=exp))

        exp_levels = int(rewards.get("exp_levels", 0) or 0)
        if exp_levels > 0:
            lines.append(self.menu_text("quest.menu.reward.levels", "&7- &f{levels} XP levels", levels=exp_levels))

        commands = len(rewards.get("commands", []) or []) + len(rewards.get("player_commands", []) or [])
        if commands > 0:
            lines.append(self.menu_text("quest.menu.reward.commands", "&7- &f{commands} command reward(s)", commands=commands))

        return lines

    def can_start_quest(self, player: Any, quest_id: str, quest: dict[str, Any]) -> bool:
        status = self.quest_status(player, quest_id)
        if status == "active":
            return False
        if status == "completed" and not bool(quest.get("repeatable", False)):
            return False
        return bool(quest.get("enabled", True))
