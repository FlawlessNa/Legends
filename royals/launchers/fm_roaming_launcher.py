"""
Used to launch any character randomly roaming in one of the Ludi FM maps.
"""
import asyncio
import botting
import royals

from royals.models_implementations.minimaps.ludi_free_market_template import LudiFreeMarketTemplate


async def main(*bots: botting.Bot) -> None:
    with botting.SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    handle = 0x009D0B92
    data = royals.RoyalsData(handle, "FarmFest1")
    data.current_minimap = LudiFreeMarketTemplate()
    data.current_minimap_area_box = data.current_minimap.get_map_area_box(handle)
    data.current_minimap_position = data.current_minimap.get_character_positions(handle).pop()
    bot1 = botting.Bot(royals.LudiFreeMarketRoaming, handle, "FarmFest1", data)
    asyncio.run(main(bot1))
