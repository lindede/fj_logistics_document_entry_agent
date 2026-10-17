# Web shipping-order samples

目录：`data/samples/web_shipping_orders/`

网上公开能直接下载的多为**空白落货纸 / Booking Note 模板**（无填写货值）。已尽量从船司、货代官网收集。

## 公开下载（空白 / 模板）

| 文件 | 来源 |
|------|------|
| `hapag_lloyd_booking_request.pdf` | [Hapag-Lloyd Booking Request Form](https://www.hapag-lloyd.com/content/dam/website/downloads/pdf/Booking_Request_Form.pdf) |
| `smyril_booking_note.pdf` | [Smyril Line Booking Note](https://www.smyrillinecargo.com/wp-content/uploads/2026/03/Booking-note.pdf) |
| `latis_shipping_order_lcl.pdf` | [Latis LCL Shipping Order](https://latis.pl/doc/latis_shipping_order_lcl_en.pdf) |
| `ts_lines_shipping_order.pdf` | [T.S. Lines Shipping Order](http://www.tslines.com.hk/download/SO.pdf) |
| `shipair_shipping_order.pdf` | [Shipair Shipping Order / Dock Receipt](https://www.shipair.com.hk/download/shipping_order.pdf) |
| `cosco_taiwan_shipping_order.pdf` | [COSCO Shipping (Taiwan) SO](http://www.coscotw.com.tw/cht/download/SO.PDF) |
| `jc_cargo_shipping_order.pdf` | [JC Cargo Shipping Order Form](https://jccargohk.com/FILE/JC%20Cargo%20-%20Shipping%20Order%20Form.pdf) |
| `fcl_booking_confirmation_sample.pdf` | 公开 FCL booking confirmation 空白模板 |

## 填好字段的演示单（本地生成）

| 文件 | 说明 |
|------|------|
| `demo_filled_shipping_order.pdf` | 虚构当事人的出口托运单样式页，带文字层；可用 `html` / `html_mix` 试抽。是否命中 `forwarder_export_so` 取决于标题条几何；未命中时 `html_struct` 会报未识别版式。**不是真实出运单。** |

商业填写过的托运单很少能免费再分发。已有金标准样张仍用仓库里的 `../BKG.pdf`。多数公开空白模板对规则抽取为 `unknown`，属预期。
