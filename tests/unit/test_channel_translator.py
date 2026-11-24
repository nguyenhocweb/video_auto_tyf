import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from src.modules.creator.video.channel_translator import ChannelMetadataTranslator


def test_sino_vietnamese_channel_names():
    # Xia Xiaopei -> Ha Tieu Phai
    res1 = ChannelMetadataTranslator.to_sino_vietnamese("夏小沛")
    assert res1 == "Hạ Tiểu Phái"

    # Li Ziqi -> Ly Tu That
    res2 = ChannelMetadataTranslator.to_sino_vietnamese("李子柒")
    assert res2 == "Lý Tử Thất"

    # Lao Wang cinema -> Lao Vuong Ke Dien Anh
    res3 = ChannelMetadataTranslator.to_sino_vietnamese("老王说电影")
    assert "Lão Vương" in res3

    # Zuo Luoluo -> Ta Lac Lac
    res4 = ChannelMetadataTranslator.to_sino_vietnamese("佐洛洛")
    assert res4 == "Tá Lạc Lạc"

    # Tsukishima Shizuku -> Nguyet Dao Van
    res5 = ChannelMetadataTranslator.to_sino_vietnamese("月岛雯")
    assert res5 == "Nguyệt Đảo Văn"

    # Gu Qianshan -> Co Thien Son
    assert ChannelMetadataTranslator.to_sino_vietnamese("顾千山") == "Cố Thiên Sơn"
    # Duan Linbeidao -> Doan Lam Bac Dao
    assert ChannelMetadataTranslator.to_sino_vietnamese("断凛北刀") == "Đoạn Lẫm Bắc Đao"


def test_chinese_name_transliteration():
    # Test common Douyin channel name combinations
    assert ChannelMetadataTranslator.to_sino_vietnamese("小妹") == "Tiểu Muội"
    assert ChannelMetadataTranslator.to_sino_vietnamese("大白") == "Đại Bạch"
    assert ChannelMetadataTranslator.to_sino_vietnamese("阿龙") == "A Long"
    assert ChannelMetadataTranslator.to_sino_vietnamese("张三") == "Trương Tam"


def test_extract_clean_name_delimited():
    # Test delimited protocol and note stripping
    raw1 = "--- NỘI DUNG ĐÃ DỊCH ---\nHạ Tiểu Phái\n--- HẾT NỘI DUNG ĐÃ DỊCH ---"
    assert ChannelMetadataTranslator._extract_clean_name(raw1) == "Hạ Tiểu Phái"

    # LLM outputs note inside block
    raw2 = "--- NỘI DUNG ĐÃ DỊCH ---\nHạ Tiểu Phái\nNote: Tên đã được chuyển đổi sang tiếng Việt\n--- HẾT NỘI DUNG ĐÃ DỊCH ---"
    assert ChannelMetadataTranslator._extract_clean_name(raw2) == "Hạ Tiểu Phái"

    # LLM outputs SároNote in-line
    raw3 = "--- NỘI DUNG ĐÃ DỊCH ---\nHạ Tiểu Phái SároNote: Tên đã được chuyển đổi sang tiếng Việt theo quy tắc đã định\n--- HẾT NỘI DUNG ĐÃ DỊCH ---"
    assert ChannelMetadataTranslator._extract_clean_name(raw3) == "Hạ Tiểu Phái"

    # Pure boilerplate
    raw4 = "--- NỘI DUNG ĐÃ DỊCH ---\nSároNote: Tên Đã Được Chuyển Đổi Sang Tiếng Việt\n--- HẾT NỘI DUNG ĐÃ DỊCH ---"
    assert ChannelMetadataTranslator._extract_clean_name(raw4) is None

    # Exact failing string from user image: delimiter skeleton without name
    raw5 = "--- NỘI DUNG ĐÃ DỊCH --- Tên Đã Dịch: --- Hết Nội Dung Đã D"
    assert ChannelMetadataTranslator._extract_clean_name(raw5) is None

    # Delimiter with cut-off tag but containing valid name
    raw6 = "--- NỘI DUNG ĐÃ DỊCH --- Tên Đã Dịch: Nguyệt Đảo Văn --- Hết Nội Dung Đã D"
    assert ChannelMetadataTranslator._extract_clean_name(raw6) == "Nguyệt Đảo Văn"


if __name__ == "__main__":
    test_sino_vietnamese_channel_names()
    test_chinese_name_transliteration()
    test_extract_clean_name_delimited()
    print("ALL CHANNEL TRANSLATOR TESTS PASSED SUCCESSFULLY!")
