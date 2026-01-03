"""
Trello API Client for Video Critique.

Provides async-compatible Trello operations for managing
video production tasks on Trello boards.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from core.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CardResult:
    """Result of a card operation."""
    success: bool
    card_id: str = ""
    error: str = ""
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


@dataclass
class ListResult:
    """Result of a list operation."""
    success: bool
    list_id: str = ""
    error: str = ""
    data: dict = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class TrelloClient:
    """
    Trello API client for video production task management.

    Provides clean interface for Trello board, list, and card operations
    with async compatibility via run_in_executor.
    """

    BASE_URL = "https://api.trello.com/1"

    def __init__(
        self,
        api_key: str,
        api_token: str,
        board_name: str | None = None,
    ):
        """
        Initialize Trello client.

        Args:
            api_key: Trello API key
            api_token: Trello API token
            board_name: Default board name for operations
        """
        self._api_key = api_key
        self._api_token = api_token
        self._board_name = board_name
        self._board_id_cache: dict[str, str] = {}
        self._list_id_cache: dict[str, dict[str, str]] = {}

    @classmethod
    def from_config(cls) -> "TrelloClient":
        """
        Create a TrelloClient from config.py settings.

        Returns:
            Configured TrelloClient instance
        """
        import config

        api_key = getattr(config, "TRELLO_API_KEY", "")
        api_token = getattr(config, "TRELLO_API_TOKEN", "")
        board_name = getattr(config, "BOARD_NAME", None)

        if not all([api_key, api_token]):
            raise ValueError(
                "Trello credentials not configured. "
                "Set TRELLO_API_KEY and TRELLO_API_TOKEN"
            )

        return cls(
            api_key=api_key,
            api_token=api_token,
            board_name=board_name,
        )

    def _get_params(self, **extra) -> dict:
        """Get base request parameters with auth."""
        params = {
            "key": self._api_key,
            "token": self._api_token,
        }
        params.update(extra)
        return params

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        **kwargs,
    ) -> requests.Response:
        """Make a request to Trello API."""
        url = f"{self.BASE_URL}{endpoint}"
        params = params or {}
        params.update(self._get_params())
        response = requests.request(method, url, params=params, **kwargs)
        response.raise_for_status()
        return response

    # ========================================================================
    # BOARD OPERATIONS
    # ========================================================================

    def get_board_id(self, board_name: str | None = None) -> str | None:
        """
        Get board ID by name.

        Args:
            board_name: Board name (uses default if not provided)

        Returns:
            Board ID or None if not found
        """
        board_name = board_name or self._board_name
        if not board_name:
            raise ValueError("No board name provided")

        # Check cache
        if board_name in self._board_id_cache:
            return self._board_id_cache[board_name]

        try:
            response = self._request("GET", "/members/me/boards")
            boards = response.json()

            for board in boards:
                if board["name"] == board_name:
                    self._board_id_cache[board_name] = board["id"]
                    return board["id"]

            logger.warning(f"[Trello] Board '{board_name}' not found")
            return None

        except Exception as e:
            logger.error(f"[Trello] Error getting board ID: {e}")
            return None

    async def get_board_id_async(self, board_name: str | None = None) -> str | None:
        """Async wrapper for get_board_id."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_board_id, board_name)

    # ========================================================================
    # LIST OPERATIONS
    # ========================================================================

    def get_lists(self, board_id: str | None = None) -> dict[str, str]:
        """
        Get all lists on a board.

        Args:
            board_id: Board ID (uses default board if not provided)

        Returns:
            Dict mapping list names to list IDs
        """
        if not board_id:
            board_id = self.get_board_id()
        if not board_id:
            return {}

        # Check cache
        if board_id in self._list_id_cache:
            return self._list_id_cache[board_id]

        try:
            response = self._request("GET", f"/boards/{board_id}/lists")
            lists = response.json()

            list_mapping = {}
            for lst in lists:
                if not lst.get("closed", False):
                    list_mapping[lst["name"]] = lst["id"]

            self._list_id_cache[board_id] = list_mapping
            return list_mapping

        except Exception as e:
            logger.error(f"[Trello] Error getting lists: {e}")
            return {}

    async def get_lists_async(self, board_id: str | None = None) -> dict[str, str]:
        """Async wrapper for get_lists."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_lists, board_id)

    def get_list_id(self, list_name: str, board_id: str | None = None) -> str | None:
        """
        Get list ID by name.

        Args:
            list_name: Name of the list
            board_id: Board ID (uses default board if not provided)

        Returns:
            List ID or None if not found
        """
        lists = self.get_lists(board_id)
        # Case-insensitive match
        for name, list_id in lists.items():
            if name.lower() == list_name.lower():
                return list_id
        return None

    async def get_list_id_async(
        self,
        list_name: str,
        board_id: str | None = None,
    ) -> str | None:
        """Async wrapper for get_list_id."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_list_id, list_name, board_id)

    def create_list(
        self,
        list_name: str,
        board_id: str | None = None,
        position: str = "bottom",
    ) -> ListResult:
        """
        Create a new list on a board.

        Args:
            list_name: Name for the new list
            board_id: Board ID (uses default board if not provided)
            position: Position ("top", "bottom", or float)

        Returns:
            ListResult with success status
        """
        if not board_id:
            board_id = self.get_board_id()
        if not board_id:
            return ListResult(success=False, error="Board not found")

        try:
            response = self._request(
                "POST",
                f"/boards/{board_id}/lists",
                params={"name": list_name, "pos": position},
            )
            data = response.json()

            # Clear cache
            self._list_id_cache.pop(board_id, None)

            return ListResult(
                success=True,
                list_id=data["id"],
                data=data,
            )

        except Exception as e:
            logger.error(f"[Trello] Error creating list: {e}")
            return ListResult(success=False, error=str(e))

    async def create_list_async(
        self,
        list_name: str,
        board_id: str | None = None,
        position: str = "bottom",
    ) -> ListResult:
        """Async wrapper for create_list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.create_list, list_name, board_id, position
        )

    def archive_list(self, list_id: str) -> bool:
        """
        Archive a list.

        Args:
            list_id: ID of the list to archive

        Returns:
            True if successful
        """
        try:
            self._request(
                "PUT",
                f"/lists/{list_id}/closed",
                params={"value": "true"},
            )
            # Clear all list caches (list might be on any board)
            self._list_id_cache.clear()
            return True

        except Exception as e:
            logger.error(f"[Trello] Error archiving list: {e}")
            return False

    async def archive_list_async(self, list_id: str) -> bool:
        """Async wrapper for archive_list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.archive_list, list_id)

    # ========================================================================
    # CARD OPERATIONS
    # ========================================================================

    def get_cards_in_list(self, list_id: str) -> list[dict]:
        """
        Get all cards in a list.

        Args:
            list_id: ID of the list

        Returns:
            List of card data dicts
        """
        try:
            response = self._request("GET", f"/lists/{list_id}/cards")
            return response.json()

        except Exception as e:
            logger.error(f"[Trello] Error getting cards in list: {e}")
            return []

    async def get_cards_in_list_async(self, list_id: str) -> list[dict]:
        """Async wrapper for get_cards_in_list."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_cards_in_list, list_id)

    def get_cards_on_board(self, board_id: str | None = None) -> list[dict]:
        """
        Get all cards on a board.

        Args:
            board_id: Board ID (uses default board if not provided)

        Returns:
            List of card data dicts
        """
        if not board_id:
            board_id = self.get_board_id()
        if not board_id:
            return []

        try:
            response = self._request("GET", f"/boards/{board_id}/cards")
            return response.json()

        except Exception as e:
            logger.error(f"[Trello] Error getting cards on board: {e}")
            return []

    async def get_cards_on_board_async(self, board_id: str | None = None) -> list[dict]:
        """Async wrapper for get_cards_on_board."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_cards_on_board, board_id)

    def get_card_by_task_number(
        self,
        task_number: int,
        board_id: str | None = None,
    ) -> dict | None:
        """
        Find a card by task number in title.

        Searches for cards with "Task #N:" in the title.

        Args:
            task_number: Task number to search for
            board_id: Board ID (uses default board if not provided)

        Returns:
            Card data dict or None if not found
        """
        cards = self.get_cards_on_board(board_id)
        search_text = f"Task #{task_number}:"

        for card in cards:
            if search_text in card.get("name", ""):
                return card

        return None

    async def get_card_by_task_number_async(
        self,
        task_number: int,
        board_id: str | None = None,
    ) -> dict | None:
        """Async wrapper for get_card_by_task_number."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.get_card_by_task_number, task_number, board_id
        )

    def create_card(
        self,
        title: str,
        description: str = "",
        list_name: str | None = None,
        list_id: str | None = None,
        due_date: datetime | None = None,
        start_date: datetime | None = None,
        board_id: str | None = None,
    ) -> CardResult:
        """
        Create a new card.

        Args:
            title: Card title
            description: Card description
            list_name: Name of list to add card to
            list_id: ID of list (overrides list_name)
            due_date: Due date for the card
            start_date: Start date for the card
            board_id: Board ID (for resolving list_name)

        Returns:
            CardResult with success status
        """
        # Resolve list ID
        if not list_id:
            if not list_name:
                return CardResult(success=False, error="No list specified")
            list_id = self.get_list_id(list_name, board_id)
            if not list_id:
                return CardResult(success=False, error=f"List '{list_name}' not found")

        try:
            params = {
                "idList": list_id,
                "name": title,
                "desc": description,
                "pos": "bottom",
            }

            if due_date:
                params["due"] = due_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if start_date:
                params["start"] = start_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")

            response = self._request("POST", "/cards", params=params)
            data = response.json()

            return CardResult(
                success=True,
                card_id=data["id"],
                data=data,
            )

        except Exception as e:
            logger.error(f"[Trello] Error creating card: {e}")
            return CardResult(success=False, error=str(e))

    async def create_card_async(
        self,
        title: str,
        description: str = "",
        list_name: str | None = None,
        list_id: str | None = None,
        due_date: datetime | None = None,
        start_date: datetime | None = None,
        board_id: str | None = None,
    ) -> CardResult:
        """Async wrapper for create_card."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.create_card(
                title, description, list_name, list_id, due_date, start_date, board_id
            ),
        )

    def update_card(self, card_id: str, **updates) -> bool:
        """
        Update a card.

        Args:
            card_id: ID of the card to update
            **updates: Fields to update (name, desc, due, idList, etc.)

        Returns:
            True if successful
        """
        try:
            self._request("PUT", f"/cards/{card_id}", params=updates)
            return True

        except Exception as e:
            logger.error(f"[Trello] Error updating card: {e}")
            return False

    async def update_card_async(self, card_id: str, **updates) -> bool:
        """Async wrapper for update_card."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.update_card(card_id, **updates)
        )

    def move_card(self, card_id: str, list_id: str) -> bool:
        """
        Move a card to a different list.

        Args:
            card_id: ID of the card to move
            list_id: ID of the destination list

        Returns:
            True if successful
        """
        return self.update_card(card_id, idList=list_id)

    async def move_card_async(self, card_id: str, list_id: str) -> bool:
        """Async wrapper for move_card."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.move_card, card_id, list_id)

    def archive_card(self, card_id: str) -> bool:
        """
        Archive a card.

        Args:
            card_id: ID of the card to archive

        Returns:
            True if successful
        """
        return self.update_card(card_id, closed="true")

    async def archive_card_async(self, card_id: str) -> bool:
        """Async wrapper for archive_card."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.archive_card, card_id)

    def set_due_complete(self, card_id: str, complete: bool) -> bool:
        """
        Set the dueComplete status on a card.

        Args:
            card_id: ID of the card
            complete: True to mark due as complete

        Returns:
            True if successful
        """
        return self.update_card(card_id, dueComplete="true" if complete else "false")

    async def set_due_complete_async(self, card_id: str, complete: bool) -> bool:
        """Async wrapper for set_due_complete."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.set_due_complete, card_id, complete)

    # ========================================================================
    # CHECKLIST OPERATIONS
    # ========================================================================

    def get_checklists(self, card_id: str) -> list[dict]:
        """
        Get all checklists on a card.

        Args:
            card_id: ID of the card

        Returns:
            List of checklist data dicts
        """
        try:
            response = self._request("GET", f"/cards/{card_id}/checklists")
            return response.json()

        except Exception as e:
            logger.error(f"[Trello] Error getting checklists: {e}")
            return []

    async def get_checklists_async(self, card_id: str) -> list[dict]:
        """Async wrapper for get_checklists."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_checklists, card_id)

    def create_checklist(
        self,
        card_id: str,
        name: str,
        items: list[dict] | None = None,
    ) -> dict | None:
        """
        Create a checklist on a card.

        Args:
            card_id: ID of the card
            name: Name of the checklist
            items: Optional list of items with keys: name, due (optional)

        Returns:
            Checklist data dict or None on error
        """
        try:
            response = self._request(
                "POST",
                "/checklists",
                params={"idCard": card_id, "name": name},
            )
            checklist = response.json()
            checklist_id = checklist["id"]

            # Add items if provided
            if items:
                for item in items:
                    item_params = {
                        "name": item["name"],
                        "pos": "bottom",
                    }
                    if "due" in item and item["due"]:
                        item_params["due"] = item["due"].strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z"
                        )

                    self._request(
                        "POST",
                        f"/checklists/{checklist_id}/checkItems",
                        params=item_params,
                    )

            return checklist

        except Exception as e:
            logger.error(f"[Trello] Error creating checklist: {e}")
            return None

    async def create_checklist_async(
        self,
        card_id: str,
        name: str,
        items: list[dict] | None = None,
    ) -> dict | None:
        """Async wrapper for create_checklist."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self.create_checklist, card_id, name, items
        )

    def update_checklist_item(
        self,
        card_id: str,
        item_id: str,
        **updates,
    ) -> bool:
        """
        Update a checklist item.

        Args:
            card_id: ID of the card
            item_id: ID of the checklist item
            **updates: Fields to update (name, due, state)

        Returns:
            True if successful
        """
        try:
            self._request(
                "PUT",
                f"/cards/{card_id}/checkItem/{item_id}",
                params=updates,
            )
            return True

        except Exception as e:
            logger.error(f"[Trello] Error updating checklist item: {e}")
            return False

    async def update_checklist_item_async(
        self,
        card_id: str,
        item_id: str,
        **updates,
    ) -> bool:
        """Async wrapper for update_checklist_item."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.update_checklist_item(card_id, item_id, **updates)
        )

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def clear_cache(self) -> None:
        """Clear all internal caches."""
        self._board_id_cache.clear()
        self._list_id_cache.clear()
