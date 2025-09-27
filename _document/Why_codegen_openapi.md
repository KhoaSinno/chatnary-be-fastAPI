# Fetch manual vs CodeGen

Giả sử backend có endpoint:

``` bash
GET /documents/suggest?q=<string>
Response 200: [{ id: number, title: string }]
```

---

## 🔹 1. Fetch truyền thống (code tay)

```ts
// src/lib/api.ts
export type SuggestItem = { id: number; title: string };

export async function suggestDocuments(q: string): Promise<SuggestItem[]> {
  const url = new URL('http://localhost:8000/documents/suggest');
  url.searchParams.set('q', q);

  const res = await fetch(url.toString(), {
    headers: {
      'X-User-Id': '1',
      'X-Request-Id': crypto.randomUUID(),
    },
  });

  if (!res.ok) throw new Error(`HTTP error! ${res.status}`);
  return res.json() as Promise<SuggestItem[]>;
}
```

👉 Ưu điểm: code ngắn, dễ hiểu.
👉 Nhược: phải viết type thủ công (`SuggestItem`), phải lặp lại pattern với mỗi API, nếu backend đổi schema → FE không biết ngay.

---

## 🔹 2. Codegen với `openapi-typescript-codegen`

Sau khi chạy:

```bash
npx openapi -i http://localhost:8000/openapi.json -o ./lib/api-client -c fetch --exportSchemas true
```

Tool sinh ra (rút gọn):

```ts
// lib/api-client/services/DocumentsService.ts
import { request as __request } from '../core/request';
import type { SuggestItem } from '../models/SuggestItem';

export class DocumentsService {
  /**
   * Suggest
   * @param q Q
   * @returns SuggestItem OK
   * @throws ApiError
   */
  public static suggestDocumentsSuggestGet({ q }: { q: string }): Promise<SuggestItem[]> {
    return __request({
      method: 'GET',
      path: `/documents/suggest`,
      query: { q },
    });
  }
}
```

👉 FE dùng:

```ts
import { DocumentsService } from '@/lib/api-client';

export async function suggestDocumentsGen(q: string) {
  return DocumentsService.suggestDocumentsSuggestGet({ q });
}
```

**Type `SuggestItem`** cũng được generate từ OpenAPI spec:

```ts
// lib/api-client/models/SuggestItem.ts
export type SuggestItem = {
  id: number;
  title: string;
};
```

---

## 🔹 So sánh

| Tiêu chí               | Fetch truyền thống                   | Codegen (`openapi-typescript-codegen`)       |
| ---------------------- | ------------------------------------ | -------------------------------------------- |
| **Code phải viết tay** | Phải tự viết mỗi function + type     | Tự động sinh toàn bộ, chỉ cần gọi service    |
| **Type an toàn**       | Phụ thuộc dev viết đúng              | Được generate từ spec, BE đổi → FE biết ngay |
| **Đồng bộ FE–BE**      | Dễ lệch nếu BE đổi mà quên update FE | FE sync tự động mỗi lần regenerate           |
| **Tốc độ dev**         | OK với 1–2 endpoint                  | Tiết kiệm rất nhiều với 10+ endpoint         |
| **Tên hàm**            | Tuỳ dev đặt (ngắn gọn, dễ đọc)       | Dựa theo `operationId`, có thể hơi dài/xấu   |
| **CI/CD**              | Không tích hợp                       | Có thể auto-gen trong pipeline               |

---

📌 Kết luận:

* Nếu chỉ 1–2 API đơn giản → **fetch tay** nhanh hơn.
* Nếu 10+ API hoặc BE đổi spec liên tục → **codegen ăn đứt** (tiết kiệm thời gian, giảm bug, sync chắc chắn).

# Why use  openapi-typescript-codegen

 **ưu – nhược điểm của `openapi-typescript-codegen`** và **tình huống sử dụng trong thực tế** :

---

## ✅ Ưu điểm

1. **Type-safe** cho FE

   * Tự động sinh `types` (request, response, params) từ OpenAPI spec.
   * Giảm bug runtime → FE gọi API sai tham số, sai kiểu dữ liệu sẽ bị TypeScript báo compile error.

2. **Sync FE–BE dễ dàng**

   * BE đổi API → cập nhật `openapi.json` → chạy codegen lại → compiler báo ngay chỗ FE dùng sai.
   * Tránh tình trạng BE trả về khác với FE nghĩ.

3. **Tự động generate services**

   * Có sẵn method tương ứng với `operationId` (ví dụ: `DocumentsService.suggestDocumentsSuggestGet`).
   * Không cần viết tay `fetch` cho từng API.

4. **Nhanh & gọn**

   * Chỉ cần một dòng script (`openapi -i URL -o lib/api-client -c fetch`).
   * Kết quả: có SDK + types để dùng ngay.

5. **Linh hoạt**

   * Nhiều mode client: `fetch`, `axios`, `node-fetch`.
   * Tùy chọn xuất schemas (`--exportSchemas true`) để dùng lại trong validation/Zod.

6. **Giảm công sức onboard dev mới**

   * Dev mới clone FE project → có SDK với docs auto-gen → biết ngay API có gì, params thế nào.

---

## ❌ Nhược điểm

1. **Codegen phình to**

   * Với spec lớn, sẽ generate hàng trăm file, khó đọc, khó merge.
   * Dùng `operationId` đặt tên xấu thì method cũng xấu (`askAskPost`, `previewDocDocumentsDocIdPreviewGet`).

2. **Phụ thuộc vào spec chuẩn**

   * Nếu BE viết OpenAPI không kỹ (thiếu schema response, operationId rác, tag không rõ) → SDK generate ra khó dùng.
   * Muốn đẹp → BE phải kỷ luật viết spec sạch.

3. **Thêm bước build**

   * Mỗi lần build/dev phải chạy codegen.
   * Nếu BE down (không fetch được spec) → FE không generate được.
   * Cách fix: commit codegen output vào repo (common practice).

4. **Boilerplate code hơi nhiều**

   * So với việc viết tay vài hàm `fetch` đơn giản, codegen có vẻ nặng nề hơn cho dự án siêu nhỏ.
   * Nhưng với >10 endpoint thì lại tiết kiệm công sức.

5. **Không phải silver bullet**

   * FE đôi khi vẫn cần wrapper để xử lý logic chung (auth, error handling, retry).
   * SDK auto-gen chưa chắc đáp ứng hết → cần viết layer API service của riêng team.

---

## 🔎 Thực tế dự án lớn & nhỏ

* **Dự án nhỏ (5–10 API endpoint, 1–2 dev):**

  * Có thể code tay (`fetch`/`axios`) cho nhanh, vì spec thay đổi không nhiều.
  * Nếu muốn học TypeScript + OpenAPI nghiêm túc → dùng codegen vẫn OK (training tốt cho team).

* **Dự án vừa (10–50 API, nhiều module):**

  * Dùng `openapi-typescript-codegen` rất hợp lý.
  * Tiết kiệm thời gian viết tay, giảm bug.
  * Dễ maintain khi BE thay đổi.

* **Dự án lớn (100+ API, nhiều team):**

  * Gần như **bắt buộc** dùng codegen (hoặc tool tương tự: `swagger-codegen`, `openapi-generator`).
  * Vì không thể maintain tay nổi.
  * SDK được generate rồi publish thành package nội bộ (`@company/api-client`), các team FE import vào xài.

👉 Nói cách khác:

* Dự án nhỏ → codegen là “nice-to-have” (có cũng tốt).
* Dự án vừa/lớn → codegen là **best practice** (gần như bắt buộc).

---

## 📌 Tại sao vẫn nên dùng?

* Nó giúp **đồng bộ hoá hợp đồng (contract)** giữa FE–BE.
* Nó giúp **giảm bug**, tăng **tốc độ phát triển**.
* Nó là một trong những bước chuẩn để “mature” hoá pipeline CI/CD (BE deploy spec → FE auto gen client).

---

👉 Tóm lại:
`openapi-typescript-codegen` **được dùng nhiều trong thực tế** (cả dự án nhỏ lẫn lớn).

* Nhỏ: học & kỷ luật.
* Lớn: gần như bắt buộc.
  Nó có nhược điểm về boilerplate & phụ thuộc spec, nhưng lợi ích type-safety và sync FE–BE là quá lớn.
