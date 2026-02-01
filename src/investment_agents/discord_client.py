"""Discord bot client for reading and writing messages."""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

import discord
from discord import Intents, Message
from discord.ext import commands

logger = logging.getLogger(__name__)


class InvestmentBot(commands.Bot):
    """Discord bot for investment tracking and updates."""

    def __init__(
        self,
        command_prefix: str = "!",
        default_channel_id: int | None = None,
    ) -> None:
        intents = Intents.default()
        intents.message_content = True
        intents.messages = True

        super().__init__(command_prefix=command_prefix, intents=intents)

        self.default_channel_id = default_channel_id
        self._message_handlers: list[Callable[[Message], Coroutine[Any, Any, None]]] = []

    async def on_ready(self) -> None:
        if self.user:
            logger.info(f"Bot logged in as {self.user.name} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

    async def on_message(self, message: Message) -> None:
        if message.author == self.user:
            return

        logger.debug(f"Message from {message.author}: {message.content[:100]}")

        for handler in self._message_handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Error in message handler: {e}")

        await self.process_commands(message)

    def add_message_handler(
        self,
        handler: Callable[[Message], Coroutine[Any, Any, None]],
    ) -> None:
        self._message_handlers.append(handler)

    async def send_to_channel(
        self,
        content: str,
        channel_id: int | None = None,
        embed: discord.Embed | None = None,
    ) -> Message | None:
        target_channel_id = channel_id or self.default_channel_id
        if not target_channel_id:
            logger.error("No channel ID specified")
            return None

        channel = self.get_channel(target_channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            logger.error(f"Channel {target_channel_id} not found")
            return None

        try:
            return await channel.send(content=content, embed=embed)
        except discord.DiscordException as e:
            logger.error(f"Failed to send message: {e}")
            return None


def create_embed(
    title: str,
    description: str | None = None,
    color: discord.Color | None = None,
    fields: list[tuple[str, str, bool]] | None = None,
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or discord.Color.blue(),
    )
    if fields:
        for name, value, inline in fields:
            embed.add_field(name=name, value=value, inline=inline)
    return embed
