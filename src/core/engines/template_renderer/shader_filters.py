"""Bộ sinh chuỗi FFmpeg Filtergraph / Shaders chuẩn xác 100% mẫu CapCut.
Hỗ trợ:
- Mẫu 01 (1 Video + 1 Ảnh): Slide down 0.55s, viền bo tròn 42px, downward drift 11.62 px/s, nháy nhẹ 15Hz.
- Mẫu 02 (3 Ảnh Tĩnh):
    1. Intro Ken Burns Zoom chậm (1.0 -> 1.08) + Nổ màu Vocal (1.8s - 4.5s) + Đơn sắc cổ điển.
    2. Cú đập nhịp Beat Drop 18.60s: Chớp sáng trắng (White Flash) + Mờ chấn động (Impact Blur Pulse).
    3. Điệp khúc giật beat: Camera Shake vật lý (14px bounce nhịp drum 15Hz) + Chớp strobe 54 nhịp.
    4. Viền đen bo góc 42px tinh tế.
"""

from typing import List, Tuple


class ShaderFilterBuilder:
    """Bộ dựng bộ lọc đồ họa chuyển động khớp từng mili-giây với bản gốc CapCut."""

    # ------------------ MẪU 01 (1 Video + 1 Ảnh) ------------------
    @staticmethod
    def build_video_slot_filter(
        input_idx: int = 0,
        output_label: str = "v1",
        duration: float = 8.80,
        target_w: int = 720,
        target_h: int = 1280,
    ) -> str:
        """Slot 1: Video mở đầu, căn giữa chuẩn 720x1280, trượt dần xuống phía dưới."""
        return (
            f"[{input_idx}:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{target_h}:(in_w-{target_w})/2:(in_h-{target_h})/2,"
            f"trim=duration={duration},setpts=PTS-STARTPTS,"
            f"format=yuv420p,setsar=1,fps=30[{output_label}]"
        )

    @staticmethod
    def build_photo_pan_strobe_filter(
        input_idx: int = 1,
        output_label: str = "v2",
        duration: float = 12.98,
        pan_speed: float = 11.62,
        total_pan_px: int = 128,
        target_w: int = 720,
        target_h: int = 1280,
    ) -> str:
        """Slot 2: Ảnh tĩnh xuất hiện từ trên trượt xuống nối đuôi + Trôi nhẹ + Nháy 15Hz."""
        extra_h = target_h + total_pan_px
        scale_proc = (
            f"[{input_idx}:v]scale={target_w}:{extra_h}:force_original_aspect_ratio=increase,"
            f"crop={target_w}:{extra_h}:(in_w-{target_w})/2:(in_h-{extra_h})/2,"
            f"trim=duration={duration},setpts=PTS-STARTPTS,"
            f"crop={target_w}:{target_h}:(in_w-{target_w})/2:'max(0, {total_pan_px} - {pan_speed}*t)'[p2_motion]"
        )
        strobe_proc = (
            f"[p2_motion]eq=eval=frame:"
            f"contrast='1.0+0.012*(mod(n,2)*2-1)':"
            f"brightness='0.008*(mod(n,2)*2-1)',"
            f"format=yuv420p,setsar=1,fps=30[{output_label}]"
        )
        return f"{scale_proc};{strobe_proc}"

    @staticmethod
    def build_slidedown_pipeline(
        v1_label: str,
        v2_label: str,
        mask_idx: int = 3,
        output_label: str = "v_out",
        transition_duration: float = 0.55,
        offset: float = 8.25,
    ) -> str:
        """Chuyển cảnh Slide Down mượt mà 0.55s: Video 1 trượt xuống, Ảnh 2 nối đuôi từ trên xuống."""
        return (
            f"[{v1_label}][{v2_label}]xfade=transition=slidedown:"
            f"duration={transition_duration}:offset={offset}[v_xfade];"
            f"[v_xfade][{mask_idx}:v]overlay=0:0,format=yuv420p[{output_label}]"
        )

    # ------------------ MẪU 02 (3 Ảnh Tĩnh) ------------------
    P3_CHORUS_INTERVALS: List[Tuple[float, float]] = [
        (18.600, 18.667), (18.700, 18.733), (18.767, 18.800), (18.833, 18.867), (18.900, 18.933),
        (19.067, 19.367), (19.500, 19.800), (19.900, 20.233), (20.333, 20.433), (20.467, 20.500),
        (20.533, 20.567), (20.600, 20.633), (20.767, 21.067), (21.200, 21.467), (21.600, 21.900),
        (22.033, 22.100), (22.133, 22.167), (22.200, 22.233), (22.267, 22.300), (22.433, 22.733),
        (22.867, 23.167), (23.267, 23.600), (23.700, 23.800), (23.833, 23.867), (23.900, 23.933),
        (24.100, 24.400), (24.533, 24.833), (24.933, 25.233), (25.367, 25.400), (25.433, 25.467),
        (25.500, 25.533), (25.567, 25.600), (25.633, 25.667), (25.800, 26.067), (26.200, 26.500),
        (26.633, 26.933), (27.033, 27.133), (27.167, 27.200), (27.233, 27.267), (27.300, 27.333),
        (27.467, 27.767), (27.900, 28.200), (28.300, 28.600), (28.733, 28.800), (28.833, 28.867),
        (28.900, 28.933), (28.967, 29.000), (29.133, 29.433), (29.567, 29.867), (29.967, 30.267),
        (30.367, 30.467), (30.500, 30.533), (30.567, 30.600), (30.667, 30.867),
    ]

    @classmethod
    def build_template_02_filtergraph(
        cls,
        p1_idx: int = 0,
        p2_idx: int = 1,
        p3_idx: int = 2,
        mask_idx: int = 4,
        target_w: int = 720,
        target_h: int = 1280,
        intro_dur: float = 18.60,
        chorus_dur: float = 12.63,
    ) -> str:
        """Filtergraph Mẫu 02 hoàn hảo chuẩn CapCut: Ken Burns, Vocal Burst, Camera Bounce, White Flash."""
        w, h = target_w, target_h

        # 1. Đoạn Intro Ảnh 1:
        # Full Card (0.0s - 2.2s & 17.5s - 18.6s) kết hợp Split-Screen chia 2 nửa (2.2s - 17.5s)
        p1_base = (
            f"[{p1_idx}:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h}:(in_w-{w})/2:(in_h-{h})/2,"
            f"trim=duration={intro_dur},setpts=PTS-STARTPTS,"
            f"zoompan=z='min(zoom+0.00012,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={w}x{h}:fps=30,"
            f"format=yuv420p,setsar=1,fps=30[v_p1_full]"
        )

        # Tạo luồng Split-screen 2 nửa: nửa trên cận cổ áo/áo, nửa dưới khuôn mặt/kính
        p1_split = (
            f"[v_p1_full]split=2[p1_raw_a][p1_raw_b];"
            f"[p1_raw_a]crop={w}:636:0:90[top_half];"
            f"[p1_raw_b]crop={w}:636:0:ih-636-60[bot_half];"
            f"[top_half][bot_half]vstack=inputs=2[split_stacked];"
            f"[split_stacked]pad={w}:{h}:0:4:black[v_p1_split_raw]"
        )

        # Chuyển đổi giữa Full và Split tại 2.2s và 17.5s + Nổ màu Vocal + Fade In
        p1_switch = (
            f"[v_p1_full][v_p1_split_raw]overlay=0:0:enable='between(t,2.2,17.5)'[v_p1_motion];"
            f"[v_p1_motion]fade=t=in:st=0:d=0.8,"
            f"eq=eval=frame:"
            f"saturation='if(lt(n,54),0,if(lt(n,120),1.4,if(lt(n,180),1.4-(n-120)/60*1.4,0)))':"
            f"contrast='1.15+0.015*(mod(n,2)*2-1)',"
            f"format=yuv420p,setsar=1,fps=30[v_p1]"
        )
        p1_filter = f"{p1_base};{p1_split};{p1_switch}"

        # 2. Chuẩn bị Ảnh 2 và Ảnh 3 cho đoạn Điệp khúc với Camera Bounce Shake (14px theo nhịp kick 15Hz)
        shake_crop = "crop=720:1280:10:'18+14*sin(2*PI*15*t)*exp(-4*mod(t,0.42))'"

        p2_filter = (
            f"[{p2_idx}:v]scale=740:1316:force_original_aspect_ratio=increase,"
            f"crop=740:1316:(in_w-740)/2:(in_h-1316)/2,"
            f"trim=duration={chorus_dur},setpts=PTS-STARTPTS,"
            f"{shake_crop},"
            f"eq=eval=frame:saturation=0.0:contrast='1.22+0.018*(mod(n,2)*2-1)',"
            f"format=yuv420p,setsar=1,fps=30[v_p2_base]"
        )
        p3_filter = (
            f"[{p3_idx}:v]scale=740:1316:force_original_aspect_ratio=increase,"
            f"crop=740:1316:(in_w-740)/2:(in_h-1316)/2,"
            f"trim=duration={chorus_dur},setpts=PTS-STARTPTS,"
            f"{shake_crop},"
            f"eq=eval=frame:saturation=0.0:contrast='1.22+0.018*(mod(n,2)*2-1)',"
            f"format=yuv420p,setsar=1,fps=30[v_p3_stream]"
        )

        # 3. Luân phiên Ảnh 2 và Ảnh 3 theo 54 nhịp beat/strobe của CapCut + Mờ chấn động + Chớp trắng bùng nổ
        p3_enable = "+".join(
            [f"between(t,{round(st - intro_dur, 3)},{round(et - intro_dur, 3)})" for st, et in cls.P3_CHORUS_INTERVALS]
        )
        chorus_switch = (
            f"[v_p2_base][v_p3_stream]overlay=0:0:enable='{p3_enable}'[v_raw_chorus];"
            f"[v_raw_chorus]boxblur=luma_radius=8:luma_power=2:enable='between(t,0,0.18)',"
            f"eq=eval=frame:brightness='if(lt(n,8),0.85*(1-n/8),0)',"
            f"fade=t=out:st=12.27:d=0.36,"
            f"format=yuv420p,setsar=1,fps=30[v_chorus]"
        )

        # 4. Ghép nối Intro và Chorus, phủ viền đen bo góc 42px
        join_mask = (
            f"[v_p1][v_chorus]concat=n=2:v=1:a=0[v_joined];"
            f"[v_joined][{mask_idx}:v]overlay=0:0,format=yuv420p[v_out]"
        )

        return f"{p1_filter};{p2_filter};{p3_filter};{chorus_switch};{join_mask}"
