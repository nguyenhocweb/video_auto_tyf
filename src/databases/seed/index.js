import { prisma } from "../init.mongodb.js";
import { cleanDatabase } from "./clean.js";
import { seedVoiceProfiles } from "./runners/01-voice-profiles.seed.js";

async function main() {
  console.log("==================================================================");
  console.log("🚀 BẮT ĐẦU SEEDING DỮ LIỆU VOICE AI STUDIO (MASTER ORCHESTRATOR)...");
  console.log("==================================================================");

  const startTime = Date.now();

  try {
    // 1. Dọn dẹp dữ liệu cũ nếu có cờ --clean
    if (process.argv.includes("--clean")) {
      await cleanDatabase();
    }

    // 2. Chạy nạp dữ liệu tuần tự
    await seedVoiceProfiles(); // [Tầng 1] Voice Profiles

    const duration = ((Date.now() - startTime) / 1000).toFixed(2);
    console.log("==================================================================");
    console.log(`🎉 HOÀN THÀNH SEED DỮ LIỆU THÀNH CÔNG TRONG ${duration} GIÂY!`);
    console.log("==================================================================");
  } catch (error) {
    console.error("🔥 LỖI TRONG QUÁ TRÌNH SEEDING DỮ LIỆU:", error);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

main();

