import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// 이 가드는 supabase 생성 타입(database.ts)이 라이브 스키마의 핵심 계약을
// 담고 있는지 강제한다. 스키마를 바꾸고 `npm run gen:types`를 빠뜨리면(또는
// 컬럼이 사라지면) 아래 런타임 검사가 실패한다.
//
// 주의: vitest는 기본적으로 타입을 체크하지 않고 제거하므로, 타입 수준 단언이
// 아니라 생성 파일의 실제 내용을 읽어 검사한다(런타임에 실효성 보장).
const dbTypes = readFileSync(
  fileURLToPath(new URL("../database.ts", import.meta.url)),
  "utf8",
);

describe("database types in sync", () => {
  it("핵심 테이블이 생성 타입에 존재한다", () => {
    for (const table of [
      "server_call_history",
      "order_details",
      "member_info",
      "setting_info",
    ]) {
      expect(dbTypes).toContain(`${table}: {`);
    }
  });

  it("핵심 컬럼이 생성 타입에 존재한다", () => {
    for (const column of ["shop_key", "processed_at", "delivery_at_text"]) {
      expect(dbTypes).toContain(column);
    }
  });

  it("Database 타입을 export 한다", () => {
    expect(dbTypes).toContain("export type Database");
  });
});
