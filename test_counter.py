import json
import unittest
from unittest.mock import MagicMock, patch

from azure.core.exceptions import ResourceNotFoundError

import function_app as fa


class TestIncrementVisitorCount(unittest.TestCase):
    def test_increments_existing_count(self):
        table_client = MagicMock()
        table_client.get_entity.return_value = {
            "PartitionKey": "counter",
            "RowKey": "1",
            "count": 41,
        }

        result = fa.increment_visitor_count(table_client)

        self.assertEqual(result, 42)
        table_client.update_entity.assert_called_once()

    def test_creates_entity_when_missing(self):
        table_client = MagicMock()
        table_client.get_entity.side_effect = ResourceNotFoundError("not found")

        result = fa.increment_visitor_count(table_client)

        self.assertEqual(result, 1)
        table_client.create_entity.assert_called_once()


class TestCounterHttpTrigger(unittest.TestCase):
    @patch("function_app._get_table_client")
    def test_returns_200_and_json_count(self, mock_get_table_client):
        mock_table_client = MagicMock()
        mock_table_client.get_entity.return_value = {
            "PartitionKey": "counter",
            "RowKey": "1",
            "count": 9,
        }
        mock_get_table_client.return_value = mock_table_client

        req = MagicMock()
        response = fa.counter(req)

        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_body())
        self.assertEqual(body["count"], 10)

    @patch("function_app._get_table_client")
    def test_returns_500_on_failure(self, mock_get_table_client):
        mock_get_table_client.side_effect = RuntimeError("connection failed")

        req = MagicMock()
        response = fa.counter(req)

        self.assertEqual(response.status_code, 500)


if __name__ == "__main__":
    unittest.main()