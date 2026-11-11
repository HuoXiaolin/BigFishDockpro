# 卡片设计参考

## 资源胶囊、AI 额度与音乐

参考 [MoFeng2223/BrimDeck](https://github.com/MoFeng2223/BrimDeck) 的 [中文说明](https://github.com/MoFeng2223/BrimDeck/blob/main/README.zh-CN.md) 与公开界面：

- AI 额度采用工具分列，配额、重置时间及今日/七日用量按固定次序呈现，模型明细单独打开。
- 音乐采用封面、两行曲名、歌词、进度和图标式控制；收起保留声音律动（也可选歌名/歌词）、配额环及资源读数。
- 资源读数按 CPU、GPU、主机分组，日/月/年流量并列，窄胶囊通过分页显示选定内容。

本应用用 PyQt 原生绘制，沿用大肥鱼Dock 的主题、字体和材质。彩色流动光环与独立开关按本次需求实现。上游数据模块为 Apache-2.0，固定提交及许可分别见 [固定版本](../references/BrimDeck-PIN.json) 和 [第三方声明](../licenses/THIRD-PARTY-NOTICES.md)。

## AI 用量统计与托盘图标

参考 [deviffyy/OpenQuota](https://github.com/deviffyy/OpenQuota) 的时间筛选、费用环图、用量趋势与分段额度图标，以及用户提供的统计界面截图。保留本应用背景和主题，以 Qt 原生绘制，并按当前数据来源提供 Token、计量记录、费用、缓存命中率与工具/模型明细。计量记录不冒充 HTTP 请求数，未提供的失败请求数不编造。

OpenQuota 仅作为设计参考，不引入其 Tauri 运行时、账号连接或网关统计后端。固定提交见 [OpenQuota-PIN.json](../references/OpenQuota-PIN.json)，MIT 原始声明见 [OpenQuota-MIT.txt](../licenses/OpenQuota-MIT.txt)。

## 液态交互与表情

贴边表面张力、拖动液桥、断开水滴和七种鼠标互动表情参考 Wisland 的设计，对应矢量与弹簧代码适配到 PyQt5。资源胶囊沿用本应用的壁纸材质、明暗主题和彩色光环。[AsamiAkito/wisland](https://github.com/AsamiAkito/wisland)

固定提交见 [Wisland-PIN.json](../references/Wisland-PIN.json)，原始版权及 MIT 许可见 [Wisland-MIT.txt](../licenses/Wisland-MIT.txt)。天气改用 Open-Meteo，消息只读取系统通知元数据和任务栏提醒事件，不读取消息正文。

## 卡片边框与翻面

桌面卡片的浅色渐变边框和点击翻面方向参考以下 Uiverse 作品，以 PyQt 绘制和交互重新实现；配色取软件主题色，文件卡片保持稳定，不使用悬停翻面。

- Cobp: https://uiverse.io/Cobp/popular-gecko-2
- joe-watson-sbf: https://uiverse.io/joe-watson-sbf/little-goat-24

## MIT License — Cobp (Fabio Cobb), joe-watson-sbf (Joseph Watzson)

Copyright (c) 2026 Cobp (Fabio Cobb)
Copyright (c) 2026 joe-watson-sbf (Joseph Watzson)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
