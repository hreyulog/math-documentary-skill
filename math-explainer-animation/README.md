# 数学科普动画 Skill

给一个题目，助手按调研、数学核对、开头设计、脚本分镜、SVG动画、音频、编码和验收推进。默认不是一次性做完整视频，而是先交付真正能播放的10—15秒首段，确认后逐段接续。

默认适配视频号与抖音：1080×1920、30fps、中文字幕、无旁白、无固定水印。可按当次要求切换横屏、时长或声音。可用于俄罗斯数学及其他数学思想；人物生平为主时使用同仓库的人物纪录片 Skill。

## 调用

```text
$math-explainer-animation
题目：为什么随机游走也有规律？
面向有高中数学基础的观众，用竖屏SVG动画讲清一个问题。
先调查资料，设计能在前五秒看懂的开头，交付15秒样片。
暂无音乐，先做静音；确认后按场景继续。
```

也可以只说“用数学动画 Skill，题目是……”，助手会先检查工作目录和已确认内容。不会把明牌示例改个标题就冒充新题成片。

## 安装

复制整个 `math-explainer-animation` 文件夹到个人 Codex skills 目录。不要只复制SKILL.md，脚本、模板和起步工程同样需要。已有同名版本先比较自己的修改；安装后新开会话，或让助手直接读取该文件。

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/.codex/skills" -Force | Out-Null
Copy-Item -LiteralPath ./math-explainer-animation -Destination "$env:USERPROFILE/.codex/skills/" -Recurse
```

```sh
mkdir -p ~/.codex/skills
cp -R math-explainer-animation ~/.codex/skills/
```

## 从工程开始

以下`<SKILL_DIR>`指实际Skill绝对路径，`<WORKSPACE>`指本次用户工作目录，执行前替换。在用户工作目录执行，不把工程建进Skill安装目录：

```sh
python "<SKILL_DIR>/scripts/init_project.py" --directory "<WORKSPACE>/my-episode" --topic "本期核心问题" --layout portrait
```

生成目录的README说明依赖安装、检查、Studio与渲染命令。示例使用Remotion4.0.536、React19.2与TypeScript，需要Node.js22+与pnpm10；通用Python工具需要Python3.10+。锁文件固定依赖，首次安装需网络。素材和输出均在新项目内，非空目录不会被覆盖。

首段示例只演示人为设定的明牌抽取，不代表真实掼蛋策略。它提供结构、图形和计算模式；新题仍须重新调查与设计。

## 音频与验证工具

```sh
python -m pip install -r "<SKILL_DIR>/requirements.txt"
python "<SKILL_DIR>/scripts/analyze_audio.py" --help
python "<SKILL_DIR>/scripts/verify_video.py" --help
node "<SKILL_DIR>/scripts/browser_check.mjs" --help
python "<SKILL_DIR>/scripts/validate_package.py"
```

音视频工具需要FFmpeg与FFprobe（可传路径或配置PATH）。浏览器检查另外需要Playwright及可用Chrome，可在生成工程中安装：

```sh
cd "<WORKSPACE>/my-episode"
pnpm add -D playwright
node "<SKILL_DIR>/scripts/browser_check.mjs" output/preview/math-preview-15s.mp4 --out qa/browser
```

模块会从当前工程查找，也可用`--playwright-module "<WORKSPACE>/my-episode/node_modules/playwright"`指定。Chrome可由`--chrome`或`CHROME_BINARY`指定；脚本不会自动下载浏览器。音乐分析只输出估计拍点；人工听审、视觉复核、实体手机和平台测试各自记录，不由自动检查代签。没有指定音乐时，首轮静音制作继续推进。

## 内容与持续更新

- `SKILL.md`：助手执行顺序和停点。
- `references/`：调研、数学边界、前五秒、动画、声音、验收与掼蛋案例。
- `templates/`：选题、脚本、分镜、来源、系列状态和验证记录。
- `assets/starter/`：可运行的Remotion与SVG示例。
- `scripts/`：初始化、音频分析、实际MP4检查、浏览器检查与发布包校验。
- `skill-package-manifest.json`：本包逐文件SHA256和大小。

本Skill提炼自已制作的竖屏数学动画：推牌、记录回看、不同历史汇合、概率分支和连续音轨。旧案例的通过记录不能用于新题；新片每轮重新核对最终文件。公开仓库没有用户私聊、个人附件、第三方音乐、原片或完整成片，实际素材在本地项目单独维护。

`templates/series.json`记录系列规划和已确认片段；`assets/starter/src/config/series.json`控制示例渲染。两者用途不同，不能直接互相覆盖。
