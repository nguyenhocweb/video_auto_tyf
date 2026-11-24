import { PrismaClient } from "./prisma/generated/prisma/index.js";

const prisma = new PrismaClient({
  log: process.env.NODE_ENV === "development" ? ["query", "error", "warn"] : ["error"],
});

export { prisma };

