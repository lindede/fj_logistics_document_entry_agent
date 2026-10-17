# 中国航运单 / 托运单样张

目录：`data/samples/cn_shipping_orders/`

## 说明

公开渠道很少能拿到可再分发的中国出口**实单**扫描件。本目录以中文落货纸 / 托运单版式为主，并填入教学用虚构字段，供 `html` / `html_mix` 等模式试抽。

`html_struct` / `html_mix` 的结构侧会先做**版式分类**：

| 样张 | `form_family` | 说明 |
|------|---------------|------|
| `cn_export_shipping_order_filled.pdf` | `forwarder_export_so` | 标题条版式接近 BKG，规则可抽 |
| `cn_container_dock_receipt_filled.pdf` | `forwarder_export_so` | 同上（场站收据风格教学页） |
| `cn_shipping_order_blank_template.pdf` | `unknown` | 栏目示意、无独立标题条；struct 不抽 |
| `cosco_taiwan_shipping_order.pdf` | `unknown` | 船司空白落货纸 |
| `cosco_taiwan_shipping_order_filled.pdf` | `unknown` | 空白上叠印教学内容；struct 不抽 |

未知版式：`html_struct` 会报错；`html_mix` 仍返回 LLM 结果，并记一条 `MIX-FORM` WARN。

## 文件

| 文件 | 说明 |
|------|------|
| `cosco_taiwan_shipping_order.pdf` | 中远海运（台湾）公开空白落货纸原件 |
| `cosco_taiwan_shipping_order_filled.pdf` | 在空白落货纸上叠印教学填写内容 |
| `cn_shipping_order_blank_template.pdf` | 中文落货纸栏目示意（已填样例） |
| `cn_export_shipping_order_filled.pdf` | 出口货物托运单（填好，标题条风格） |
| `cn_container_dock_receipt_filled.pdf` | 集装箱货物托运单/场站收据风格（填好，标题条风格） |

业务金标准实样仍用：`../BKG.pdf`（`forwarder_export_so`）。
