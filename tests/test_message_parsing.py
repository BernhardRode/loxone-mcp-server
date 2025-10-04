"""
Unit tests for message parsing functionality.

Tests cover:
- Binary message decoding
- Text message parsing
- State update message processing
- Malformed message error handling
- Message type detection
- Encoding detection and handling
"""

import json
import struct
import uuid
from unittest.mock import Mock, patch
import pytest

from loxone_mcp.loxone_client import (
    LoxoneClient,
    MessageType,
    check_and_decode_if_needed,
    detect_encoding,
    ConnectionState,
)
from loxone_mcp.config import LoxoneConfig


class TestEncodingDetection:
    """Test encoding detection and message decoding utilities."""
    
    def test_detect_encoding_utf8(self):
        """Test detecting UTF-8 encoding."""
        utf8_bytes = "Hello, 世界!".encode("utf-8")
        encoding = detect_encoding(utf8_bytes)
        assert encoding == "utf-8"
    
    def test_detect_encoding_latin1(self):
        """Test detecting Latin-1 encoding."""
        latin1_bytes = "Café".encode("latin-1")
        encoding = detect_encoding(latin1_bytes)
        # Should detect as latin-1 or iso-8859-1 (they're equivalent)
        assert encoding in ["latin-1", "iso-8859-1"]
    
    def test_detect_encoding_ascii(self):
        """Test detecting ASCII encoding."""
        ascii_bytes = "Hello World".encode("ascii")
        encoding = detect_encoding(ascii_bytes)
        # ASCII is a subset of UTF-8, so UTF-8 will be detected first
        assert encoding == "utf-8"
    
    def test_detect_encoding_invalid_bytes(self):
        """Test detecting encoding for invalid byte sequences."""
        invalid_bytes = b'\xff\xfe\x00\x00\x01\x02\x03'
        encoding = detect_encoding(invalid_bytes)
        # Should find some encoding that can handle these bytes
        assert encoding is not None
    
    def test_detect_encoding_empty_bytes(self):
        """Test detecting encoding for empty byte string."""
        empty_bytes = b''
        encoding = detect_encoding(empty_bytes)
        assert encoding == "utf-8"  # Empty string is valid UTF-8
    
    def test_check_and_decode_if_needed_string(self):
        """Test that string input is returned unchanged."""
        text = "Already a string"
        result = check_and_decode_if_needed(text)
        assert result == text
        assert isinstance(result, str)
    
    def test_check_and_decode_if_needed_utf8_bytes(self):
        """Test decoding UTF-8 bytes."""
        text = "Hello, 世界!"
        utf8_bytes = text.encode("utf-8")
        result = check_and_decode_if_needed(utf8_bytes)
        assert result == text
        assert isinstance(result, str)
    
    def test_check_and_decode_if_needed_latin1_bytes(self):
        """Test decoding Latin-1 bytes when UTF-8 fails."""
        text = "Café"
        latin1_bytes = text.encode("latin-1")
        
        # This should fail UTF-8 decoding and fall back to encoding detection
        result = check_and_decode_if_needed(latin1_bytes)
        assert result == text
        assert isinstance(result, str)
    
    def test_check_and_decode_if_needed_invalid_bytes(self):
        """Test handling of completely invalid byte sequences."""
        invalid_bytes = b'\xff\xfe\x00\x00\x01\x02\x03'
        
        # Should not crash and return some decoded string
        result = check_and_decode_if_needed(invalid_bytes)
        assert isinstance(result, str)
        # Content may be garbled but should not crash
    
    def test_check_and_decode_if_needed_undecodable_bytes(self):
        """Test handling when no encoding can decode the bytes."""
        # Create bytes that can't be decoded by any common encoding
        undecodable_bytes = bytes([0xFF, 0xFE, 0xFD, 0xFC])
        
        with patch('loxone_mcp.loxone_client.detect_encoding', return_value=None):
            result = check_and_decode_if_needed(undecodable_bytes)
            assert isinstance(result, str)
            # Should use UTF-8 with error replacement
            assert "�" in result or len(result) > 0


class TestMessageTypeDetection:
    """Test message type detection and header parsing."""
    
    def test_message_type_enum_values(self):
        """Test that MessageType enum has expected values."""
        assert MessageType.TextMessage.value == 0
        assert MessageType.BinaryFile.value == 1
        assert MessageType.EventTableValueStates.value == 2
        assert MessageType.EventTableTextStates.value == 3
        assert MessageType.EventTableDaytimerStates.value == 4
        assert MessageType.OutOfService.value == 5
        assert MessageType.Keepalive.value == 6
        assert MessageType.EventTableWeatherStates.value == 7
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_valid_header(self):
        """Test parsing valid Loxone message header."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create a valid 8-byte header for EventTableValueStates (type 2)
        header = struct.pack("ccccI", b'\x03', b'\x02', b'\x00', b'\x00', 0)
        
        await client._parse_loxone_message(header)
        
        assert client._current_message_type == MessageType.EventTableValueStates
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_text_message(self):
        """Test parsing header for text message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create header for TextMessage (type 0)
        header = struct.pack("ccccI", b'\x03', b'\x00', b'\x00', b'\x00', 0)
        
        await client._parse_loxone_message(header)
        
        assert client._current_message_type == MessageType.TextMessage
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_keepalive(self):
        """Test parsing header for keepalive message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create header for Keepalive (type 6)
        header = struct.pack("ccccI", b'\x03', b'\x06', b'\x00', b'\x00', 0)
        
        await client._parse_loxone_message(header)
        
        assert client._current_message_type == MessageType.Keepalive
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_unknown_type(self):
        """Test parsing header with unknown message type."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create header with unknown message type (99)
        header = struct.pack("ccccI", b'\x03', b'\x63', b'\x00', b'\x00', 0)
        
        await client._parse_loxone_message(header)
        
        # Should default to TextMessage for unknown types
        assert client._current_message_type == MessageType.TextMessage
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_invalid_length(self):
        """Test parsing message with invalid header length."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create header with wrong length (should be 8 bytes)
        invalid_header = b'\x03\x02\x00\x00'  # Only 4 bytes
        
        await client._parse_loxone_message(invalid_header)
        
        # Should default to TextMessage for invalid headers
        assert client._current_message_type == MessageType.TextMessage
    
    @pytest.mark.asyncio
    async def test_parse_loxone_message_malformed_header(self):
        """Test parsing malformed message header."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create malformed header that will cause struct.error
        malformed_header = b'\x03\x02\x00'  # Too short for struct.unpack
        
        await client._parse_loxone_message(malformed_header)
        
        # Should default to TextMessage for malformed headers
        assert client._current_message_type == MessageType.TextMessage


class TestValueStatesParsing:
    """Test parsing of binary value state updates."""
    
    def test_parse_value_states_single_update(self):
        """Test parsing a single value state update."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create a test UUID and value
        test_uuid = uuid.uuid4()
        test_value = 42.5
        
        # Create binary message: 16 bytes UUID (little-endian) + 8 bytes double
        uuid_bytes = test_uuid.bytes_le
        value_bytes = struct.pack("d", test_value)
        message = uuid_bytes + value_bytes
        
        result = client._parse_value_states(message)
        
        # Convert UUID to expected format
        fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
        expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
        
        assert len(result) == 1
        assert expected_uuid in result
        assert result[expected_uuid] == test_value
    
    def test_parse_value_states_multiple_updates(self):
        """Test parsing multiple value state updates."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create multiple test UUIDs and values
        test_data = [
            (uuid.uuid4(), 10.0),
            (uuid.uuid4(), 25.5),
            (uuid.uuid4(), -5.2),
        ]
        
        # Create binary message with multiple updates
        message = b''
        for test_uuid, test_value in test_data:
            uuid_bytes = test_uuid.bytes_le
            value_bytes = struct.pack("d", test_value)
            message += uuid_bytes + value_bytes
        
        result = client._parse_value_states(message)
        
        assert len(result) == 3
        
        for test_uuid, test_value in test_data:
            fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
            expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
            assert expected_uuid in result
            assert result[expected_uuid] == test_value
    
    def test_parse_value_states_empty_message(self):
        """Test parsing empty value states message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        result = client._parse_value_states(b'')
        
        assert result == {}
    
    def test_parse_value_states_incomplete_message(self):
        """Test parsing incomplete value states message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create incomplete message (only 20 bytes instead of 24)
        test_uuid = uuid.uuid4()
        incomplete_message = test_uuid.bytes_le + b'\x00\x00\x00\x00'  # Missing 4 bytes
        
        result = client._parse_value_states(incomplete_message)
        
        # Should return empty dict for malformed message
        assert result == {}
    
    def test_parse_value_states_malformed_message(self):
        """Test parsing malformed value states message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create malformed message that will cause parsing errors
        malformed_message = b'\x00' * 16 + b'\xff\xff\xff\xff\xff\xff\xff\xff'
        
        # Should not crash and return empty dict
        result = client._parse_value_states(malformed_message)
        assert isinstance(result, dict)


class TestTextStatesParsing:
    """Test parsing of binary text state updates."""
    
    def test_parse_text_states_single_update(self):
        """Test parsing a single text state update."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create test data
        test_uuid = uuid.uuid4()
        icon_uuid = uuid.uuid4()
        test_text = "Hello World"
        
        # Create binary message
        message = b''
        message += test_uuid.bytes_le  # 16 bytes: UUID
        message += icon_uuid.bytes_le  # 16 bytes: Icon UUID
        message += struct.pack("<I", len(test_text))  # 4 bytes: text length
        message += test_text.encode("utf-8")  # N bytes: text content
        
        # Add padding to 4-byte boundary
        total_size = 16 + 16 + 4 + len(test_text)
        padding = (4 - (total_size % 4)) % 4
        message += b'\x00' * padding
        
        result = client._parse_text_states(message)
        
        # Convert UUID to expected format
        fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
        expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
        
        assert len(result) == 1
        assert expected_uuid in result
        assert result[expected_uuid] == test_text
    
    def test_parse_text_states_multiple_updates(self):
        """Test parsing multiple text state updates."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create test data
        test_data = [
            (uuid.uuid4(), "First text"),
            (uuid.uuid4(), "Second text"),
            (uuid.uuid4(), "Third text with special chars: äöü"),
        ]
        
        # Create binary message with multiple updates
        message = b''
        for test_uuid, test_text in test_data:
            icon_uuid = uuid.uuid4()
            text_bytes = test_text.encode("utf-8")
            
            message += test_uuid.bytes_le  # UUID
            message += icon_uuid.bytes_le  # Icon UUID
            message += struct.pack("<I", len(text_bytes))  # Text length
            message += text_bytes  # Text content
            
            # Add padding
            total_size = 16 + 16 + 4 + len(text_bytes)
            padding = (4 - (total_size % 4)) % 4
            message += b'\x00' * padding
        
        result = client._parse_text_states(message)
        
        assert len(result) == 3
        
        for test_uuid, test_text in test_data:
            fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
            expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
            assert expected_uuid in result
            assert result[expected_uuid] == test_text
    
    def test_parse_text_states_empty_text(self):
        """Test parsing text state update with empty text."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create test data with empty text
        test_uuid = uuid.uuid4()
        icon_uuid = uuid.uuid4()
        test_text = ""
        
        # Create binary message
        message = b''
        message += test_uuid.bytes_le  # UUID
        message += icon_uuid.bytes_le  # Icon UUID
        message += struct.pack("<I", 0)  # Text length = 0
        # No text content
        # No padding needed (total size is already multiple of 4)
        
        result = client._parse_text_states(message)
        
        fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
        expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
        
        assert len(result) == 1
        assert expected_uuid in result
        assert result[expected_uuid] == ""
    
    def test_parse_text_states_empty_message(self):
        """Test parsing empty text states message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        result = client._parse_text_states(b'')
        
        assert result == {}
    
    def test_parse_text_states_malformed_message(self):
        """Test parsing malformed text states message."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create malformed message (incomplete header)
        malformed_message = b'\x00' * 20  # Not enough bytes for complete header
        
        # Should not crash and return empty dict
        result = client._parse_text_states(malformed_message)
        assert result == {}


class TestMessageContentParsing:
    """Test parsing of different message content types."""
    
    @pytest.mark.asyncio
    async def test_parse_message_content_text_message(self):
        """Test parsing text message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.TextMessage
        
        # Test with JSON content
        json_data = {"LL": {"control": "dev/sps/io/test", "value": "1", "Code": "200"}}
        json_message = json.dumps(json_data).encode("utf-8")
        
        result = await client._parse_message_content(json_message)
        
        assert result == json_data
    
    @pytest.mark.asyncio
    async def test_parse_message_content_text_message_invalid_json(self):
        """Test parsing text message with invalid JSON."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.TextMessage
        
        # Test with invalid JSON
        invalid_json = b"not valid json content"
        
        result = await client._parse_message_content(invalid_json)
        
        # Should return text content when JSON parsing fails
        assert result == {"text": "not valid json content"}
    
    @pytest.mark.asyncio
    async def test_parse_message_content_value_states(self):
        """Test parsing value states message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.EventTableValueStates
        
        # Create test value states message
        test_uuid = uuid.uuid4()
        test_value = 123.45
        message = test_uuid.bytes_le + struct.pack("d", test_value)
        
        result = await client._parse_message_content(message)
        
        assert isinstance(result, dict)
        assert len(result) == 1
        # Should contain the parsed UUID and value
        uuid_key = list(result.keys())[0]
        assert result[uuid_key] == test_value
    
    @pytest.mark.asyncio
    async def test_parse_message_content_text_states(self):
        """Test parsing text states message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.EventTableTextStates
        
        # Create test text states message
        test_uuid = uuid.uuid4()
        icon_uuid = uuid.uuid4()
        test_text = "Test Status"
        text_bytes = test_text.encode("utf-8")
        
        message = b''
        message += test_uuid.bytes_le
        message += icon_uuid.bytes_le
        message += struct.pack("<I", len(text_bytes))
        message += text_bytes
        
        result = await client._parse_message_content(message)
        
        assert isinstance(result, dict)
        assert len(result) == 1
        uuid_key = list(result.keys())[0]
        assert result[uuid_key] == test_text
    
    @pytest.mark.asyncio
    async def test_parse_message_content_keepalive(self):
        """Test parsing keepalive message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.Keepalive
        
        result = await client._parse_message_content(b'')
        
        assert result == {"keepalive": True}
    
    @pytest.mark.asyncio
    async def test_parse_message_content_binary_file(self):
        """Test parsing binary file message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.BinaryFile
        
        binary_data = b'\x00\x01\x02\x03\x04\x05'
        result = await client._parse_message_content(binary_data)
        
        assert result == {"binary_file": True, "size": 6}
    
    @pytest.mark.asyncio
    async def test_parse_message_content_out_of_service(self):
        """Test parsing out of service message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.OutOfService
        
        result = await client._parse_message_content(b'')
        
        assert result == {"out_of_service": True}
    
    @pytest.mark.asyncio
    async def test_parse_message_content_daytimer_states(self):
        """Test parsing daytimer states message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.EventTableDaytimerStates
        
        result = await client._parse_message_content(b'some_daytimer_data')
        
        # Should return dict (implementation may vary)
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_parse_message_content_weather_states(self):
        """Test parsing weather states message content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.EventTableWeatherStates
        
        result = await client._parse_message_content(b'some_weather_data')
        
        # Should return dict (implementation may vary)
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_parse_message_content_exception_handling(self):
        """Test that parsing exceptions are handled gracefully."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        client._current_message_type = MessageType.EventTableValueStates
        
        # Create malformed message that will cause parsing error
        malformed_message = b'\x00\x01\x02'  # Too short for value states
        
        result = await client._parse_message_content(malformed_message)
        
        # Should return None or empty dict, not crash
        assert result is None or result == {}


class TestMessageParsingIntegration:
    """Test integration of message parsing components."""
    
    @pytest.mark.asyncio
    async def test_full_message_parsing_flow(self):
        """Test complete message parsing flow from header to content."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create a complete message with header and content
        # Header for EventTableValueStates
        header = struct.pack("ccccI", b'\x03', b'\x02', b'\x00', b'\x00', 24)
        
        # Content: single value state update
        test_uuid = uuid.uuid4()
        test_value = 99.9
        content = test_uuid.bytes_le + struct.pack("d", test_value)
        
        # Parse header first
        await client._parse_loxone_message(header)
        assert client._current_message_type == MessageType.EventTableValueStates
        
        # Parse content
        result = await client._parse_message_content(content)
        
        # Verify result
        assert isinstance(result, dict)
        assert len(result) == 1
        
        fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
        expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
        assert expected_uuid in result
        assert result[expected_uuid] == test_value
    
    @pytest.mark.asyncio
    async def test_error_recovery_after_malformed_message(self):
        """Test that client recovers after processing malformed messages."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Process malformed header
        malformed_header = b'\x00\x01\x02'  # Too short
        await client._parse_loxone_message(malformed_header)
        
        # Should default to TextMessage
        assert client._current_message_type == MessageType.TextMessage
        
        # Should still be able to process valid messages
        valid_header = struct.pack("ccccI", b'\x03', b'\x06', b'\x00', b'\x00', 0)
        await client._parse_loxone_message(valid_header)
        
        assert client._current_message_type == MessageType.Keepalive
    
    def test_uuid_formatting_consistency(self):
        """Test that UUID formatting is consistent across parsing functions."""
        config = LoxoneConfig(
            host="test.local",
            port=80,
            username="test",
            password="test"
        )
        client = LoxoneClient(config)
        
        # Create test UUID
        test_uuid = uuid.uuid4()
        
        # Test value states parsing
        value_message = test_uuid.bytes_le + struct.pack("d", 42.0)
        value_result = client._parse_value_states(value_message)
        value_uuid_key = list(value_result.keys())[0]
        
        # Test text states parsing
        icon_uuid = uuid.uuid4()
        test_text = "test"
        text_bytes = test_text.encode("utf-8")
        text_message = test_uuid.bytes_le + icon_uuid.bytes_le + struct.pack("<I", len(text_bytes)) + text_bytes
        text_result = client._parse_text_states(text_message)
        text_uuid_key = list(text_result.keys())[0]
        
        # UUID formatting should be consistent
        assert value_uuid_key == text_uuid_key
        
        # Verify expected format
        fields = test_uuid.urn.replace("urn:uuid:", "").split("-")
        expected_uuid = f"{fields[0]}-{fields[1]}-{fields[2]}-{fields[3]}{fields[4]}"
        assert value_uuid_key == expected_uuid