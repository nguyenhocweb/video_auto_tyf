import logging
from typing import List, Dict, Any

logger = logging.getLogger("storyboard_beat_library")


def generate_progressive_story_beats(
    topic: str,
    art_info: Dict[str, str],
    genre_info: Dict[str, str],
    scene_count: int,
) -> List[Dict[str, Any]]:
    """
    Sinh kịch bản mạch truyện liền mạch, tiến triển liên tục, KHÔNG LẶP LẠI (tối đa 60 cảnh).
    Tuân theo mô hình Hook -> Deep Dive -> Twists -> Resolution -> Outro.
    """
    style_pfx = art_info.get("style_prefix", "")
    hero = art_info.get("protagonist_dna", "character")
    sidekick = art_info.get("companion_dna", "companion")

    # 60 nhịp kể chuyện tuần tự, hoàn toàn không trùng lặp
    beats_data = [
        (f"Bạn có bao giờ thắc mắc về {topic} hay chưa?", f"{style_pfx} Curious opening shot. {hero} looking up at question marks."),
        ("Nhiều người nghĩ rằng mọi thứ rất đơn giản, nhưng thực tế lại khác.", f"{style_pfx} Comparison view. {hero} observing unexpected details."),
        ("Khi đi sâu tìm hiểu, có những bí mật cực kỳ thú vị dần được hé lộ.", f"{style_pfx} Discovery shot. {hero} holding magnifying glass with {sidekick}."),
        ("Hóa ra ngay từ thời xa xưa, điều này đã gắn liền mật thiết với đời sống.", f"{style_pfx} Flashback scene. {hero} looking at ancient story wall art."),
        ("Thời đó, con người không có những điều kiện tiện nghi như bây giờ.", f"{style_pfx} Primal environment. {hero} standing in wild rugged nature."),
        ("Họ phải đối mặt với vô vàn hiểm nguy rình rập mỗi khi đêm buông xuống.", f"{style_pfx} Suspenseful shadows. Glowing animal eyes peering in dark."),
        ("Thế nhưng, tổ tiên chúng ta đã có những cách sinh tồn cực kỳ quái chiêu.", f"{style_pfx} Clever survival scene. {hero} preparing ancient tools."),
        ("Những phát hiện khảo cổ gần đây đã chứng minh sự thật kinh ngạc đó.", f"{style_pfx} Dig site. {hero} and {sidekick} brushing dust off artifact."),
        ("Các nhà khoa học ban đầu cũng không dám tin vào những bằng chứng này.", f"{style_pfx} Lab setting. {hero} examining microscopic evidence in surprise."),
        ("Nhưng các lớp trầm tích hóa thạch đã kể lại câu chuyện hoàn toàn khác.", f"{style_pfx} Strata visualization. Floating layers revealing footprints."),
        ("Không chỉ vậy, cơ thể con người khi đó cũng thích nghi rất đặc biệt.", f"{style_pfx} Diagram visual. {hero} observing animated brain synapses."),
        ("Một nửa bán cầu não vẫn luôn thức để cảnh giác với mọi tiếng động lạ.", f"{style_pfx} Night watch. {hero} sleeping with one eye alert, radar waves."),
        ("Hiện tượng kỳ lạ này ngày nay vẫn còn sót lại trong tiềm thức chúng ta.", f"{style_pfx} Bedroom scene. {hero} tossing and turning, ancient memories."),
        ("Ví dụ như khi bạn ngủ ở một nơi xa lạ và cảm thấy rất khó ngủ.", f"{style_pfx} Hotel room. {hero} looking at unfamiliar clock, alert posture."),
        ("Đó chính là cơ chế tự vệ nguyên thủy được truyền lại qua hàng triệu năm.", f"{style_pfx} Timeline spiral. {hero} connected by golden threads to past."),
        ("Bước sang các giai đoạn sau, con người bắt đầu có những bước chuyển biến lớn.", f"{style_pfx} Era of innovation. {hero} discovering fire with warm glow."),
        ("Họ bắt đầu biết quây quần bên đống lửa ấm áp để bảo vệ lẫn nhau.", f"{style_pfx} Campfire circle. {hero} and {sidekick} sharing warmth under stars."),
        ("Họ dùng tro tàn và thảo mộc thiên nhiên để xua đuổi côn trùng độc hại.", f"{style_pfx} Herbal brewing. Aromatic smoke rising from ancient bowl."),
        ("Những chiếc nệm đầu tiên trong lịch sử loài người cũng từ đó mà ra đời.", f"{style_pfx} Primitive bedding. {hero} testing mattress of fragrant leaves."),
        ("Chúng được lót bằng nhiều lớp lá cây có mùi tinh dầu thư giãn tinh thần.", f"{style_pfx} Lush flora. Green medicinal leaves releasing calming particles."),
        ("Tất nhiên, hành trình ấy chưa bao giờ bằng phẳng và dễ dàng.", f"{style_pfx} Sudden storm. {hero} shielding the fire with determination."),
        ("Mỗi biến cố thời tiết lại mang đến những thử thách mới cần giải quyết.", f"{style_pfx} Problem solving. {hero} sketching shelter blueprints on sand."),
        ("Nhưng sự kiên trì và trí thông minh đã giúp con người luôn tìm ra lối đi.", f"{style_pfx} Breakthrough. {hero} holding up sturdy protective canopy."),
        ("So với ngày xưa, cuộc sống hiện đại mang lại quá nhiều điều kiện tuyệt vời.", f"{style_pfx} Split screen comparing ancient rugged cave with cozy room."),
        ("Thế nhưng đôi khi, chính sự dư dả lại khiến chúng ta tự tạo thêm áp lực.", f"{style_pfx} Modern overwhelm. {hero} surrounded by buzzing notifications."),
        ("Chúng ta mải miết chạy theo những thước đo vô hình mà quên mất bản thân.", f"{style_pfx} Hamster wheel metaphor. {hero} running fast reaching for stars."),
        ("Đôi khi, giải pháp tốt nhất chỉ đơn giản là học cách dừng lại và thả lỏng.", f"{style_pfx} Zen moment. {hero} taking deep mindful breath on green hill."),
        ("Hãy nhìn lại hành trình dài để thấy mỗi chúng ta đã kiên cường đến mức nào.", f"{style_pfx} Looking back at mountain path. {hero} gazing at path overcome."),
        ("Mỗi khoảnh khắc bình yên hôm nay đều là thành quả đáng trân trọng.", f"{style_pfx} Peaceful moment. {hero} sipping warm cup of tea by cozy window."),
        ("Sự thật là bạn không cần phải hoàn hảo để cảm thấy hạnh phúc.", f"{style_pfx} Acceptance and joy. {hero} smiling at imperfect happy reflection."),
        ("Đôi khi, hạnh phúc chỉ là được sống trọn vẹn với nhịp điệu của chính mình.", f"{style_pfx} Carefree dance. {hero} and {sidekick} jumping under confetti."),
        ("Những điều giản dị quanh ta mới chính là gốc rễ của sự bình an bền vững.", f"{style_pfx} Grounded tree metaphor. {hero} resting against giant oak tree."),
        ("Nhiều nghiên cứu hiện đại cũng chỉ ra sự tương đồng thú vị này.", f"{style_pfx} Scientific study graph. Infographic chart showing well-being peaks."),
        ("Khi cơ thể được nghỉ ngơi hợp lý, trí não sẽ tự phục hồi năng lượng phi thường.", f"{style_pfx} Energy recharge. Glowing aura surrounding {hero} in recovery."),
        ("Đó là lý do vì sao những ý tưởng sáng tạo nhất thường đến lúc bạn thư thả.", f"{style_pfx} Sudden inspiration. Bright lightbulb igniting above {hero} head."),
        ("Đừng ngần ngại cho bản thân những khoảng lặng cần thiết giữa cuộc sống bận rộn.", f"{style_pfx} Sanctuary space. {hero} reclining comfortably with soft light."),
        ("Bởi vì nghỉ ngơi không phải là từ bỏ, mà là nạp năng lượng cho chặng đường xa.", f"{style_pfx} Recharging battery symbol. {hero} ready for next adventure."),
        ("Mỗi thử thách bạn đang trải qua hôm nay cũng chỉ là một phân cảnh nhỏ.", f"{style_pfx} Film reel metaphor. {hero} holding movie strip of life chapters."),
        ("Quan trọng là cách chúng ta lựa chọn bước tiếp với sự lạc quan và tò mò.", f"{style_pfx} Optimistic forward stride. {hero} walking toward archway."),
        ("Hãy luôn giữ cho mình tinh thần khám phá như những đứa trẻ ngày thơ bé.", f"{style_pfx} Childhood wonder. {hero} blowing dandelion seeds into starry sky."),
        ("Thế giới này rộng lớn và luôn chứa đựng những điều kỳ diệu chờ bạn trải nghiệm.", f"{style_pfx} Cosmic horizon. {hero} on cliff gazing at aurora borealis."),
        ("Bạn mạnh mẽ và kiên cường hơn rất nhiều so với những gì bạn từng tự nghĩ.", f"{style_pfx} Inner strength visual. Giant courageous golden shadow of {hero}."),
        ("Hãy tin tưởng vào hành trình riêng của mình, dù nó không giống bất kỳ ai.", f"{style_pfx} Unique path. {hero} taking scenic wildflower path."),
        ("Mỗi bước chân bạn đi đều đang kiến tạo nên câu chuyện độc nhất của chính bạn.", f"{style_pfx} Glowing footsteps. Luminous golden flowers along the ground."),
        ("Đừng quên sẻ chia nụ cười và năng lượng tích cực này đến những người xung quanh.", f"{style_pfx} Warm community. {hero} handing glowing lantern to passerby."),
        ("Vì niềm vui khi được lan tỏa sẽ luôn nhân lên gấp bội lần.", f"{style_pfx} Ripple effect of smiles. Multiple stickman friends high-fiving."),
        ("Cuộc sống vốn dĩ là một bức tranh muôn màu do chính bạn lựa chọn nét vẽ.", f"{style_pfx} Giant canvas. {hero} holding paintbrush painting vibrant hues."),
        ("Hãy tô điểm cho nó bằng sự dũng cảm, lòng bao dung và yêu thương chân thành.", f"{style_pfx} Heart motif. {hero} placing warm heart gem on monument."),
        ("Mỗi ngày trôi qua đều là một cơ hội tuyệt vời để bắt đầu lại tốt hơn.", f"{style_pfx} Sunrise. Golden dawn sunlight illuminating {hero} face with hope."),
        ("Hãy hít thật sâu, mỉm cười và sẵn sàng đón nhận những điều tốt đẹp đang tới.", f"{style_pfx} Ready for greatness. {hero} opening arms wide on hilltop."),
        ("Hy vọng câu chuyện hôm nay đã mang lại cho bạn những phút giây thư giãn bổ ích.", f"{style_pfx} Friendly presentation. {hero} bowing politely with grateful expression."),
        ("Những bài học từ quá khứ sẽ luôn là kim chỉ nam soi sáng cho hiện tại.", f"{style_pfx} Glowing ancient compass. {hero} holding compass toward north star."),
        ("Hãy luôn trân quý bản thân và tận hưởng từng khoảnh khắc đáng giá này.", f"{style_pfx} Twilight contentment. {hero} sitting beside peaceful campfire."),
        ("Mỗi một trải nghiệm dù nhỏ bé cũng đều có ý nghĩa sâu sắc của riêng nó.", f"{style_pfx} Symbolic mosaic. Small colorful glass tiles forming masterpiece."),
        ("Chúc bạn luôn có những giấc ngủ ngon và ngập tràn năng lượng mỗi sớm mai.", f"{style_pfx} Dreamy star clouds. {hero} sleeping peacefully under moon."),
        ("Hãy nhớ rằng: Ngày mai sẽ luôn là một ngày mới với vô vàn điều kỳ diệu đón chờ.", f"{style_pfx} Dawn gate. Magical doorway opening into world of wonders."),
        ("Nếu bạn thấy video này thú vị và hữu ích, đừng tiếc một lượt chia sẻ nhé.", f"{style_pfx} Friendly thumbs-up. {hero} giving cheerful thumbs-up to camera."),
        ("Sự ủng hộ của bạn là nguồn động lực to lớn nhất để tạo ra thêm nhiều nội dung.", f"{style_pfx} Shower of gratitude. Floating hearts and stars around {hero}."),
        ("Bạn có góc nhìn hay trải nghiệm nào về điều này không? Hãy bình luận nhé!", f"{style_pfx} Engaging discussion bubble. Floating chat dialogue boxes."),
        ("Cảm ơn bạn đã luôn đồng hành. Hẹn gặp lại bạn trong những câu chuyện tiếp theo!", f"{style_pfx} Final memorable outro shot. {hero} and {sidekick} waving happily."),
    ]

    result = []
    total_beats = len(beats_data)
    effective_count = min(total_beats, max(3, scene_count))

    for i in range(effective_count):
        narr, p_en = beats_data[i]
        result.append({
            "scene_idx": i + 1,
            "narration": narr,
            "prompt_en": p_en,
            "estimated_duration": 3.0,
        })

    # Nếu người dùng yêu cầu số cảnh vượt quá 60 (ví dụ 65 cảnh)
    if scene_count > total_beats:
        for j in range(total_beats, scene_count):
            extra_idx = (j % total_beats) + 1
            result.append({
                "scene_idx": j + 1,
                "narration": f"Chi tiết mở rộng số {j + 1} về chủ đề {topic} giúp chúng ta hiểu sâu sắc hơn.",
                "prompt_en": f"{style_pfx} Extended depth chapter {j + 1}. {hero} exploring further fascinating historical horizons.",
                "estimated_duration": 3.0,
            })

    return result
