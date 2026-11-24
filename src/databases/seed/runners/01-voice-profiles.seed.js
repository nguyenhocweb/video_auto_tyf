import { prisma } from "../../init.mongodb.js";
import masterProfiles from "../data/voice_profiles_master.json" assert { type: "json" };

export async function seedVoiceProfiles() {
  console.log("👉 [Tầng 1] Đang khởi tạo Master Voice Profiles (Kho giọng mẫu sẵn)...");

  for (const item of masterProfiles) {
    const existing = await prisma.voiceProfile.findFirst({
      where: { profileName: item.profileName },
    });

    if (!existing) {
      await prisma.voiceProfile.create({
        data: item,
      });
      console.log(`  + Đã tạo hồ sơ giọng mẫu: ${item.profileName}`);
    } else {
      console.log(`  = Đã tồn tại: ${item.profileName}`);
    }
  }

  console.log("✅ [Tầng 1] Hoàn thành Voice Profiles.");
}

