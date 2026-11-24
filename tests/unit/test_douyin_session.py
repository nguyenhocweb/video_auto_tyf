import unittest
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.modules.creator.douyin.schemas import (
    DouyinSessionStatusResponse,
    DouyinQrStartResponse,
    DouyinQrStatusResponse,
    DouyinSubmitCodeRequest,
    DouyinSendCodeRequest,
)
from src.modules.creator.douyin.repository import DouyinMongoRepository


class TestDouyinSession(unittest.TestCase):
    def test_schemas_validation(self):
        status = DouyinSessionStatusResponse(
            is_connected=True,
            nickname="Test User",
            avatar_url="https://example.com/avatar.jpg",
            uid="12345678",
            sec_uid="MS4wLjABAAAA...",
            last_connected_at="2026-11-11T19:50:00+07:00",
        )
        self.assertTrue(status.is_connected)
        self.assertEqual(status.nickname, "Test User")
        self.assertEqual(status.uid, "12345678")

        qr_start = DouyinQrStartResponse(
            session_id="test-session-uuid",
            qr_code_url="data:image/png;base64,iVBORw0KGgo...",
            expires_in=120,
            status="WAITING_FOR_SCAN",
        )
        self.assertEqual(qr_start.session_id, "test-session-uuid")
        self.assertEqual(qr_start.expires_in, 120)

        qr_status = DouyinQrStatusResponse(
            session_id="test-session-uuid",
            status="NEED_VERIFY",
            message="Yêu cầu mã xác minh OTP",
            masked_mobile="138****8888",
            account_info=None,
        )
        self.assertEqual(qr_status.status, "NEED_VERIFY")
        self.assertEqual(qr_status.masked_mobile, "138****8888")

        submit_req = DouyinSubmitCodeRequest(
            session_id="test-session-uuid",
            code="123456",
        )
        self.assertEqual(submit_req.code, "123456")

        send_req = DouyinSendCodeRequest(session_id="test-session-uuid")
        self.assertEqual(send_req.session_id, "test-session-uuid")

    def test_repository_doc_to_dict(self):
        raw_doc = {
            "_id": "67324b1234567890abcdef12",
            "user_id": "user123",
            "nickname": "Creator",
            "uid": "12345",
            "is_active": True,
            "created_at": "2026-11-11 19:50:00",
        }
        converted = DouyinMongoRepository._doc_to_dict(raw_doc)
        self.assertIsNotNone(converted)
        self.assertEqual(converted["id"], "67324b1234567890abcdef12")
        self.assertNotIn("_id", converted)
        self.assertEqual(converted["nickname"], "Creator")


if __name__ == "__main__":
    unittest.main()
