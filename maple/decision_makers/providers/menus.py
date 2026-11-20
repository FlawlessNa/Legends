"""
The client's menus: the ability menu, with the character's speed and jump it
shows, the inventory menu, and the equipment window, with the weapon it shows.

`AbilityMenuProvider` and `InventoryMenuProvider` serve them (#443). Each is
built once per Bot, when a DecisionMaker reads one of its keys
(`AbilityPointDistributor` reads the ability menu's). Nothing reads the
inventory's yet: it waits for the parked `InventoryManager` to be ported.

They are two Providers because the ability menu's setup opens the menu, reads
it and closes it, while the inventory's reads the client as it is, which shows no
inventory: a Bot that only levels up must not read one.

**The multipliers.** `SPEED_MULTIPLIER` and `JUMP_MULTIPLIER` are what the
ability menu shows, read once at setup, while it is open, and never refreshed on
their own. They are not the profile's `speed_multiplier` and `jump_multiplier`:
those stay the `BotData` statics `MapleBot.child_init` sets, for a Bot that
builds no ability menu. `PathingProvider.physics()` takes the menu's when the
Bot read them, the profile's when it did not.
"""

from botting.core import HANDLE, Key, Provider
from botting.core.errors import StartupRefused
from game_data.catalogue.model import WeaponData
from maple.actions import ensure_ability_menu_displayed, ensure_equipment_menu_displayed
from maple.model.interface import AbilityMenu, InventoryMenu
from maple.screen.equipment import load_equipment_reader

from .client import FRAME


class AbilityMenuProvider(Provider):
    """
    Serves the ability menu and what it shows. `setup()` opens the menu, reads
    the available AP, speed and jump off it while it is open, and closes it.
    """

    needs = (FRAME, HANDLE)
    #: Seconds the menu has to open, and to close, at setup.
    TIME_LIMIT = 2.0

    def setup(self) -> None:
        menu = AbilityMenu()
        identifier = f"{self} - Ability Menu Setup"
        condition = self.proxies.instance(identifier, "Condition")

        self.register(ABILITY_MENU, lambda: menu, initial_value=menu)
        self.register(
            ABILITY_MENU_DISPLAYED,
            lambda: menu.is_displayed(self.read(HANDLE), self.read(FRAME).pixels),
            initial_value=False,
        )
        self._display(menu, identifier, condition, ensure_displayed=True)
        self.register(
            AVAILABLE_AP,
            lambda: menu.get_available_ap(self.read(HANDLE), self.read(FRAME).pixels),
        )
        self.register(
            SPEED_MULTIPLIER,
            lambda: menu.get_speed(self.read(HANDLE), self.read(FRAME).pixels),
        )
        self.register(
            JUMP_MULTIPLIER,
            lambda: menu.get_jump(self.read(HANDLE), self.read(FRAME).pixels),
        )
        self._display(menu, identifier, condition, ensure_displayed=False)

    def _display(
        self,
        menu: AbilityMenu,
        identifier: str,
        condition: object,
        *,
        ensure_displayed: bool,
    ) -> None:
        ensure_ability_menu_displayed(
            identifier=identifier,
            handle=self.read(HANDLE),
            ign=self.data.ign,
            pipe=self.pipe,
            menu=menu,
            condition=condition,  # pyright: ignore[reportArgumentType] - a Manager Condition
            timeout=self.TIME_LIMIT,
            ensure_displayed=ensure_displayed,
        )


#: The ability menu's reader.
ABILITY_MENU: Key[AbilityMenu] = Key("ability_menu", AbilityMenuProvider)
#: Whether the ability menu is open. Refreshed only when asked to.
ABILITY_MENU_DISPLAYED: Key[bool] = Key("ability_menu_displayed", AbilityMenuProvider)
#: The ability points available, as the menu showed them at setup. A DecisionMaker
#: refreshes it while the menu is open.
AVAILABLE_AP: Key[int | None] = Key("available_ap", AbilityMenuProvider)
#: The character's speed, as a fraction, as the ability menu showed it at setup.
SPEED_MULTIPLIER: Key[float] = Key("ability_menu_speed", AbilityMenuProvider)
#: The character's jump, as a fraction, as the ability menu showed it at setup.
JUMP_MULTIPLIER: Key[float] = Key("ability_menu_jump", AbilityMenuProvider)


class EquipmentMenuProvider(Provider):
    """
    Serves the weapon the character holds. `setup()` opens the equipment window
    with the `Equipment Menu` key, reads the weapon slot, and closes it, as the
    ability menu's does. Built only when a DecisionMaker reads `WEAPON`: a Bot
    with no weapon-based attack never opens the window.

    There is no fallback to the profile (#631, D11): a weapon that can't be read
    refuses the start, saying whether the window wasn't found or no icon matched.
    """

    needs = (FRAME, HANDLE)
    #: Seconds the window has to open, and to close, at setup.
    TIME_LIMIT = 2.0

    def setup(self) -> None:
        reader = load_equipment_reader()
        identifier = f"{self} - Equipment Menu Setup"
        condition = self.proxies.instance(identifier, "Condition")

        def display(*, ensure_displayed: bool) -> None:
            ensure_equipment_menu_displayed(
                identifier=identifier,
                handle=self.read(HANDLE),
                ign=self.data.ign,
                pipe=self.pipe,
                reader=reader,
                condition=condition,  # pyright: ignore[reportArgumentType] - a Manager Condition
                timeout=self.TIME_LIMIT,
                ensure_displayed=ensure_displayed,
            )

        try:
            display(ensure_displayed=True)
        except TimeoutError as error:
            raise StartupRefused(
                "the weapon can't be read: the equipment window did not open "
                f"({error}). Check that 'Equipment Menu' in keybindings.ini is "
                "the key the client opens it with"
            ) from error
        reading = reader.read(self.read(FRAME))
        display(ensure_displayed=False)
        if reading.value is None:
            raise StartupRefused(f"the weapon can't be read: {reading.detail}")
        weapon = reading.value
        self.register(WEAPON, lambda: weapon, initial_value=weapon)


#: The weapon the character holds, read once at setup.
WEAPON: Key[WeaponData] = Key("weapon", EquipmentMenuProvider)


class InventoryMenuProvider(Provider):
    """
    Serves the inventory menu and what it shows: the mesos and the active tab
    are read at setup, the rest start with a value, and each is refreshed when
    asked to.
    """

    needs = (FRAME, HANDLE)

    def setup(self) -> None:
        menu = InventoryMenu()

        self.register(INVENTORY_MENU, lambda: menu, initial_value=menu)
        self.register(
            INVENTORY_MENU_DISPLAYED,
            lambda: menu.is_displayed(self.read(HANDLE), self.read(FRAME).pixels),
            initial_value=False,
        )
        self.register(
            INVENTORY_MENU_EXTENDED,
            lambda: menu.is_extended(self.read(HANDLE), self.read(FRAME).pixels),
            initial_value=False,
        )
        self.register(CURRENT_MESOS, lambda: menu.get_current_mesos(self.read(HANDLE)))
        self.register(
            INVENTORY_MENU_ACTIVE_TAB,
            lambda: menu.get_active_tab(self.read(HANDLE), self.read(FRAME).pixels),
        )
        self.register(
            INVENTORY_SPACE_LEFT,
            lambda: menu.get_space_left(self.read(HANDLE), self.read(FRAME).pixels),
            initial_value=menu.total_slots,
        )


#: The inventory menu's reader.
INVENTORY_MENU: Key[InventoryMenu] = Key("inventory_menu", InventoryMenuProvider)
INVENTORY_MENU_DISPLAYED: Key[bool] = Key(
    "inventory_menu_displayed", InventoryMenuProvider
)
INVENTORY_MENU_EXTENDED: Key[bool] = Key(
    "inventory_menu_extended", InventoryMenuProvider
)
CURRENT_MESOS: Key[int | None] = Key("current_mesos", InventoryMenuProvider)
INVENTORY_MENU_ACTIVE_TAB: Key[str | None] = Key(
    "inventory_menu_active_tab", InventoryMenuProvider
)
INVENTORY_SPACE_LEFT: Key[int | None] = Key(
    "inventory_space_left", InventoryMenuProvider
)
