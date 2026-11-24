import { prisma } from "../init.mongodb.js";

export async function cleanDatabase() {
  console.log("🧹 Đang dọn dẹp sạch dữ liệu cũ theo đúng thứ tự phụ thuộc...");

  // Xóa theo thứ tự từ bảng con đến bảng cha
  await prisma.audioGeneration.deleteMany();
  await prisma.voiceProfile.deleteMany();
  await prisma.voiceSample.deleteMany();

  console.log("✅ Đã dọn dẹp sạch toàn bộ dữ liệu âm thanh cũ!");
}

