# 外部方法与按需读取

这些入口补充技术和表达方法。本系列的核心仍是：调查可靠资料、说明模型条件、用统一计算解释一个问题，实际渲染并验收，再按确认范围继续。此页是自行编写的方法映射，不包含上游代码或大段原文。

核对日期：2026-10-16。已读取提交与许可检查见 [upstream-lock.json](../upstream-lock.json)。远端主分支以后可能变化；需要新 API 时重新核对并记录，不自动升级已有工程。

## 先按任务选入口

| 当前需要 | 首选入口 | 在本系列中怎样使用 |
| --- | --- | --- |
| 判断该读哪一项 Remotion 指引 | 官方 `remotion-best-practices` | 只作路由，继续读取与当前任务有关的子项 |
| 编写场景、逐帧移动、字体、字幕和音频 | 官方 `remotion-markup`；字幕问题另看 `remotion-captions` | 按工程已锁定版本查 API，保持可复现、手机可读和完整数据绑定 |
| 查当前 API 与导出方法 | 官方 `remotion-docs`、`remotion-render` | 实际读取相应文档；保留现有依赖锁和用户要求的 MP4 交付 |
| 动作杂乱、太急或缺乏注意力重点 | `animation-basics` | 一次强调一个变化，加入平缓加减速与理解停顿 |
| 观众只看到公式结果、看不见如何计算 | 中文 `remotion-video` 的“过程动画模式”及相应脚本指南 | 输入可辨认→操作可见→结果进入明确位置→留时间核对；首次详细，重复适当加速 |

本机已安装时，从当前 Skills 清单读取其实际 `SKILL.md`；不要把此页中的仓库相对路径当作本机绝对路径。安装的官方 Skills 会引用相应 `REFERENCE.md`，按照它给出的真实相对路径继续读取。没有安装时，可直接读取下面的已核对入口；不为阅读而复制整仓或执行安装脚本。

## 1. Remotion 官方：技术依据

- 仓库与安装说明：[remotion-dev/skills](https://github.com/remotion-dev/skills)。
- 已读路由：[remotion-best-practices/SKILL.md](https://github.com/remotion-dev/skills/blob/1441a11e95db35443bd76bb318386c0d3ca00053/skills/remotion-best-practices/SKILL.md)。该入口声明版本 `4.0.536`。
- 已读实现入口：[remotion-markup/SKILL.md](https://github.com/remotion-dev/skills/blob/1441a11e95db35443bd76bb318386c0d3ca00053/skills/remotion-markup/SKILL.md)。
- 已读渲染入口：[remotion-render/SKILL.md](https://github.com/remotion-dev/skills/blob/1441a11e95db35443bd76bb318386c0d3ca00053/skills/remotion-render/SKILL.md)。
- API 另查 [Remotion 官方文档](https://www.remotion.dev/docs)。

采用其中的帧驱动、时间换算、资源引用、音频裁切与渲染知识。不要因外部示例包含某组件就将正在使用的场景全面迁移；先检查工程实际版本、任务收益和兼容性。已有工程不因读取创建入口而重建。

官方路由倾向于先提供 Studio 预览，仅在明确要求时导出。这个系列已明确要求实际可播放 MP4，因此应在约定片段范围内执行渲染和最终文件验收；不能只交预览或计划。TTS、3D、地图、SaaS、升级和云服务只在当前任务明确需要时读取，不能因为入口提及就自动执行。

核对时 API 未报告仓库许可证，递归树也未发现 LICENSE 文件；本包只链接和自行概括，不内置官方文件。该检查不用于推断 Remotion 框架本身的许可条件。

## 2. animation-basics：节奏与连续性

- 实际名称：`animation-basics`，位于 `motion-graphics-fundamentals/`。
- 已读入口：[SKILL.md](https://github.com/abusuraihsakhri/agentic-video-skills/blob/ae1847566d62c5f43ef50cbf34050f0eeaba31a7/motion-graphics-fundamentals/SKILL.md)。
- 已核对：[Apache-2.0 许可证](https://github.com/abusuraihsakhri/agentic-video-skills/blob/ae1847566d62c5f43ef50cbf34050f0eeaba31a7/LICENSE)。本包未复制该文件或代码。

本系列选用三点：同一时刻有明确主动作，运动有自然起止，完成后允许停顿。对象搬运可用不遮挡其他对象的短弧线，镜头仅在确实帮助阅读时移动。所有动作仍由视频帧计算。

不将动画原理机械套用到数学图形。概率条、面积和坐标承担数值含义，挤压、拉伸或超调会改变信息。严肃默认风格不采用弹跳、装饰性光影或夸张变形。不能为了“动画原则”让概率短暂越界，或让几何条件在过渡中失效却不说明。

## 3. 中文 remotion-video：让计算发生在眼前

- 仓库：[wshuyi/remotion-video-skill](https://github.com/wshuyi/remotion-video-skill)。
- 已读入口：[SKILL.md](https://github.com/wshuyi/remotion-video-skill/blob/d16ebd9ca330d636cf82bfd33d48ae12df74fadd/SKILL.md)，按需定位“过程动画模式”“脚本撰写指南（过程动画版）”与过程动画常见问题。
- 已读中文说明：[README_CN.md](https://github.com/wshuyi/remotion-video-skill/blob/d16ebd9ca330d636cf82bfd33d48ae12df74fadd/README_CN.md)。

自行实现适合本题的 SVG 过程：先标出输入和当前操作，再让变化发生，将输出放进明确的结果区域。第一遍给足观察时间，后续重复在不省略新条件的前提下加快。字幕给条件和结论，动作承担计算；具体值、条长和字幕仍来自本项目同一计算函数。

它的入口覆盖 TTS、三维组件等更宽泛流程，本系列默认无旁白、优先二维 SVG，因此只取相关方法。不自动运行其音频脚本、申请密钥、生成声音、上传素材或调用收费服务。即使示例可运行，也应重新核对进度边界、帧确定性、数学与现有 API，不能照搬后免检。

中文 README 标注 MIT，但核对时 API 未识别许可证、递归树也没有独立 LICENSE 文件；本包只链接和自行概括，不复制其代码或模板，也不将 README 声明写成已验证的完整授权。

## 应用后怎样验收

在本片的 `brief.md` 或制作记录中写明实际采用哪一方法、对应哪个镜头、改善什么理解问题。已有旧版保持可播放，新版单独输出。逐帧检查中途轨迹、定量关系、字幕和必要条件，实际查看最终编码画面；有音乐时单独记录技术分析与是否听审。外部方法的使用记录不能替代本片自己的数学和播放验证。
