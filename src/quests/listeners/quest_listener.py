import time
from typing import Any

from endstone.event import (
    ActorDamageEvent,
    ActorDeathEvent,
    BlockBreakEvent,
    BlockCookEvent,
    BlockPlaceEvent,
    EventPriority,
    PlayerDeathEvent,
    PlayerPickupItemEvent,
    PlayerInteractActorEvent,
    PlayerInteractEvent,
    PlayerItemConsumeEvent,
    PlayerJoinEvent,
    PlayerMoveEvent,
    event_handler,
)

from quests.managers import QuestManager


class QuestListener:
    COOKER_BLOCKS = {
        "minecraft:furnace",
        "minecraft:lit_furnace",
        "minecraft:blast_furnace",
        "minecraft:lit_blast_furnace",
        "minecraft:smoker",
        "minecraft:lit_smoker",
        "minecraft:campfire",
        "minecraft:soul_campfire",
    }
    FISH_ITEMS = {
        "minecraft:cod",
        "minecraft:raw_fish",
        "minecraft:salmon",
        "minecraft:raw_salmon",
        "minecraft:tropical_fish",
        "minecraft:clownfish",
        "minecraft:pufferfish",
    }
    SHEARABLE_ACTORS = {
        "minecraft:sheep",
        "minecraft:mooshroom",
        "minecraft:snow_golem",
        "minecraft:bogged",
    }
    TAME_ITEMS_BY_ACTOR = {
        "minecraft:wolf": {"minecraft:bone"},
        "minecraft:cat": {"minecraft:cod", "minecraft:raw_fish", "minecraft:salmon", "minecraft:raw_salmon"},
        "minecraft:ocelot": {"minecraft:cod", "minecraft:raw_fish", "minecraft:salmon", "minecraft:raw_salmon"},
        "minecraft:parrot": {
            "minecraft:wheat_seeds",
            "minecraft:melon_seeds",
            "minecraft:pumpkin_seeds",
            "minecraft:beetroot_seeds",
            "minecraft:torchflower_seeds",
        },
        "minecraft:horse": {
            "minecraft:wheat",
            "minecraft:sugar",
            "minecraft:apple",
            "minecraft:golden_carrot",
            "minecraft:golden_apple",
        },
        "minecraft:donkey": {
            "minecraft:wheat",
            "minecraft:sugar",
            "minecraft:apple",
            "minecraft:golden_carrot",
            "minecraft:golden_apple",
        },
        "minecraft:mule": {
            "minecraft:wheat",
            "minecraft:sugar",
            "minecraft:apple",
            "minecraft:golden_carrot",
            "minecraft:golden_apple",
        },
        "minecraft:llama": {"minecraft:wheat", "minecraft:hay_block"},
        "minecraft:trader_llama": {"minecraft:wheat", "minecraft:hay_block"},
    }
    BREED_ITEMS_BY_ACTOR = {
        "minecraft:armadillo": {"minecraft:spider_eye"},
        "minecraft:bee": {
            "minecraft:dandelion",
            "minecraft:poppy",
            "minecraft:blue_orchid",
            "minecraft:allium",
            "minecraft:azure_bluet",
            "minecraft:red_tulip",
            "minecraft:orange_tulip",
            "minecraft:white_tulip",
            "minecraft:pink_tulip",
            "minecraft:oxeye_daisy",
            "minecraft:cornflower",
            "minecraft:lily_of_the_valley",
            "minecraft:sunflower",
            "minecraft:lilac",
            "minecraft:rose_bush",
            "minecraft:peony",
            "minecraft:torchflower",
        },
        "minecraft:camel": {"minecraft:cactus"},
        "minecraft:cat": {"minecraft:cod", "minecraft:raw_fish", "minecraft:salmon", "minecraft:raw_salmon"},
        "minecraft:chicken": {
            "minecraft:wheat_seeds",
            "minecraft:melon_seeds",
            "minecraft:pumpkin_seeds",
            "minecraft:beetroot_seeds",
            "minecraft:torchflower_seeds",
        },
        "minecraft:cow": {"minecraft:wheat"},
        "minecraft:donkey": {"minecraft:golden_carrot", "minecraft:golden_apple"},
        "minecraft:fox": {"minecraft:sweet_berries", "minecraft:glow_berries"},
        "minecraft:frog": {"minecraft:slime_ball"},
        "minecraft:goat": {"minecraft:wheat"},
        "minecraft:hoglin": {"minecraft:crimson_fungus"},
        "minecraft:horse": {"minecraft:golden_carrot", "minecraft:golden_apple"},
        "minecraft:llama": {"minecraft:hay_block"},
        "minecraft:mooshroom": {"minecraft:wheat"},
        "minecraft:mule": {"minecraft:golden_carrot", "minecraft:golden_apple"},
        "minecraft:ocelot": {"minecraft:cod", "minecraft:raw_fish", "minecraft:salmon", "minecraft:raw_salmon"},
        "minecraft:panda": {"minecraft:bamboo"},
        "minecraft:pig": {"minecraft:carrot", "minecraft:potato", "minecraft:beetroot"},
        "minecraft:rabbit": {"minecraft:carrot", "minecraft:golden_carrot", "minecraft:dandelion"},
        "minecraft:sheep": {"minecraft:wheat"},
        "minecraft:sniffer": {"minecraft:torchflower_seeds"},
        "minecraft:strider": {"minecraft:warped_fungus"},
        "minecraft:turtle": {"minecraft:seagrass"},
        "minecraft:wolf": {
            "minecraft:beef",
            "minecraft:chicken",
            "minecraft:cooked_beef",
            "minecraft:cooked_chicken",
            "minecraft:cooked_mutton",
            "minecraft:cooked_porkchop",
            "minecraft:cooked_rabbit",
            "minecraft:mutton",
            "minecraft:porkchop",
            "minecraft:rabbit",
            "minecraft:rotten_flesh",
        },
    }

    def __init__(self, manager: QuestManager):
        self.manager = manager
        self.cooker_users: dict[str, dict[str, Any]] = {}
        self.interaction_cooldowns: dict[str, float] = {}

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_join(self, event: PlayerJoinEvent):
        self.manager.start_auto_quests(event.player)

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_block_break(self, event: BlockBreakEvent):
        self.manager.progress_objective(
            event.player,
            "break",
            1,
            self.manager.block_type_id(event.block),
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_block_place(self, event: BlockPlaceEvent):
        block_type = self.manager.block_type_id(getattr(event, "block_placed_state", None))
        if not block_type:
            block_type = self.manager.block_type_id(event.block)

        self.manager.progress_objective(event.player, "place", 1, block_type)

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_move(self, event: PlayerMoveEvent):
        distance = self.manager.distance_between(event.from_location, event.to_location)
        minimum = float(self.manager.config.get("settings", {}).get("walk_min_distance", 0.05))
        maximum = float(self.manager.config.get("settings", {}).get("walk_max_distance_per_event", 5.0))
        if distance < minimum or distance > maximum:
            return

        self.manager.progress_objective(event.player, "walk", distance)

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_actor_damage(self, event: ActorDamageEvent):
        player = self.manager.source_player(event.damage_source)
        if player is None:
            return

        victim_type = self.manager.actor_type_id(event.actor)
        self.manager.progress_objective(
            player,
            "deal_damage",
            float(event.damage),
            victim_type,
            {"damage_type": getattr(event.damage_source, "type", "")},
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_actor_death(self, event: ActorDeathEvent):
        if self.manager.is_player_actor(event.actor):
            return

        player = self.manager.source_player(event.damage_source)
        if player is None:
            return

        self.manager.progress_objective(
            player,
            "mob_kill",
            1,
            self.manager.actor_type_id(event.actor),
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_death(self, event: PlayerDeathEvent):
        player = self.manager.source_player(event.damage_source)
        if player is None or self.manager.player_key(player) == self.manager.player_key(event.player):
            return

        self.manager.progress_objective(
            player,
            "player_kill",
            1,
            "minecraft:player",
            {"victim_name": event.player.name},
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_item_consume(self, event: PlayerItemConsumeEvent):
        self.manager.progress_objective(
            event.player,
            "consume",
            int(max(1, getattr(event.item, "amount", 1))),
            self.manager.item_type_id(event.item),
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_pickup_item(self, event: PlayerPickupItemEvent):
        item_stack = getattr(event.item, "item_stack", None)
        item_type = self.manager.item_type_id(item_stack)
        if item_type not in self.FISH_ITEMS:
            return

        self.manager.progress_objective(
            event.player,
            "fish",
            int(max(1, getattr(item_stack, "amount", 1))),
            item_type,
        )

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_interact_actor(self, event: PlayerInteractActorEvent):
        actor_type = self.manager.actor_type_id(event.actor)
        item_type = self.held_item_type_id(event.player)
        if not item_type:
            return

        meta = {"source": item_type, "item": item_type}
        if item_type == "minecraft:shears" and actor_type in self.SHEARABLE_ACTORS:
            if not self.interaction_on_cooldown(event.player, "shear", event.actor, item_type):
                self.manager.progress_objective(event.player, "shear", 1, actor_type, meta)
            return

        if item_type in self.TAME_ITEMS_BY_ACTOR.get(actor_type, set()):
            if not self.interaction_on_cooldown(event.player, "tame", event.actor, item_type):
                self.manager.progress_objective(event.player, "tame", 1, actor_type, meta)
            return

        if item_type in self.BREED_ITEMS_BY_ACTOR.get(actor_type, set()):
            if not self.interaction_on_cooldown(event.player, "breed", event.actor, item_type):
                self.manager.progress_objective(event.player, "breed", 1, actor_type, meta)

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_player_interact(self, event: PlayerInteractEvent):
        if not event.has_block:
            return

        block_type = self.manager.block_type_id(event.block)
        if block_type not in self.COOKER_BLOCKS:
            return

        self.cooker_users[self.block_key(event.block)] = {
            "player": event.player,
            "time": time.time(),
        }

    @event_handler(priority=EventPriority.MONITOR, ignore_cancelled=True)
    def on_block_cook(self, event: BlockCookEvent):
        credit = self.cooker_users.get(self.block_key(event.block))
        if credit is None:
            return

        max_age = float(self.manager.config.get("settings", {}).get("smelt_credit_seconds", 600))
        if time.time() - float(credit.get("time", 0)) > max_age:
            return

        player = credit.get("player")
        if player is None:
            return

        self.manager.progress_objective(
            player,
            "smelt",
            int(max(1, getattr(event.result, "amount", 1))),
            self.manager.item_type_id(event.result),
            {"source": self.manager.item_type_id(event.source), "result": self.manager.item_type_id(event.result)},
        )

    def block_key(self, block: Any) -> str:
        try:
            dimension = str(block.dimension.name).lower()
        except Exception:
            dimension = "unknown"
        return f"{dimension}:{int(block.x)}:{int(block.y)}:{int(block.z)}"

    def held_item_type_id(self, player: Any) -> str:
        try:
            main_hand = player.inventory.item_in_main_hand
        except Exception:
            main_hand = None

        item_type = self.manager.item_type_id(main_hand)
        if item_type:
            return item_type

        try:
            off_hand = player.inventory.item_in_off_hand
        except Exception:
            off_hand = None

        return self.manager.item_type_id(off_hand)

    def interaction_on_cooldown(self, player: Any, objective_type: str, actor: Any, item_type: str) -> bool:
        cooldown_key = f"{self.manager.player_key(player)}:{objective_type}:{getattr(actor, 'id', 0)}:{item_type}"
        now = time.time()
        if self.interaction_cooldowns.get(cooldown_key, 0.0) > now:
            return True

        self.interaction_cooldowns[cooldown_key] = now + 0.75
        return False
