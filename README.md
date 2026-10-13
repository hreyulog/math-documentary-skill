# math-documentary-skill

用于制作数学人物纪录短片的 Codex skill：以人物生平与贡献为主线，输出真实、可播放的竖屏视频。

当前 skill：[st-petersburg-math-documentary](st-petersburg-math-documentary/SKILL.md)。适用于圣彼得堡数学家及相近科学人物，默认中文男声、中文在上英文在下的双语字幕。

## 安装

先克隆仓库：

```sh
git clone https://github.com/hreyulog/math-documentary-skill.git
cd math-documentary-skill
```

将整个 `st-petersburg-math-documentary` 文件夹复制到个人 Codex skills 目录。Windows PowerShell：

```powershell
New-Item -ItemType Directory -Path "$env:USERPROFILE/.codex/skills" -Force | Out-Null
Copy-Item -LiteralPath ./st-petersburg-math-documentary -Destination "$env:USERPROFILE/.codex/skills/" -Recurse
```

macOS / Linux：

```sh
mkdir -p ~/.codex/skills
cp -R st-petersburg-math-documentary ~/.codex/skills/
```

若已有同名 skill，请先比较版本和自己的修改。安装后新开一个会话；也可以让助手直接读取该目录的 `SKILL.md`。

## 调用示例

```text
$st-petersburg-math-documentary
制作一条介绍马尔可夫生平和贡献的90秒中文竖屏纪录片。
采用中文男声，上中文下英文字幕，结合历史照片与可使用的视频片段。
交付可播放MP4、高清版、字幕、素材来源、封面及核对报告。
```

用户要求全套时，制作约90秒主推版和5–6分钟完整版。人物、时长、声音与素材以用户本次要求为准。

## 制作流程

1. 核实人物事实及数学贡献，完成中文旁白与逐句英文。
2. 登记素材作者、来源页、许可和年代，区分历史资料、当代画面和情景再现。
3. 生成旁白与实际时间轴，再制作镜头、双语字幕及连续音频混合。
4. 输出9:16、H.264/AAC、恒定帧率MP4，并生成小于15,000,000字节的播放副本。
5. 核对最终文件的完整解码、音轨、真实编码帧，以及史实、英译和素材来源。
6. 补齐封面、旁白稿、来源页、播放入口和最终文件清单。

本地技术脚本负责音视频及技术验证；封面、网页和史实、英译、许可复核由执行 skill 的助手完成。自动报告不会把这些复核自动标记为通过。详见 [使用说明](st-petersburg-math-documentary/README.md) 与 [核对流程](st-petersburg-math-documentary/references/verification.md)。

## 本地脚本

依赖 Python、Pillow、edge-tts 和 FFmpeg。语音合成需要网络，已有旁白 WAV 和准确字幕时可采用离线路径。可指定现有 FFmpeg 或使用 imageio-ffmpeg。

```sh
cd st-petersburg-math-documentary
python -m pip install -r requirements.txt
python scripts/video_runtime.py doctor
python scripts/video_runtime.py build --project /absolute/path/project.json
```

从 [配置示例](st-petersburg-math-documentary/examples/project.example.json) 创建独立项目，填入核实过的内容和素材路径。相对路径以项目配置所在目录解析。可用 `--ffmpeg`、`--vendor` 等参数指定现有工具；准确字段和分步命令以 `--help` 为准。

## 已验证范围

这套流程已用于切比雪夫制作，并完成马尔可夫90秒独立试作：中文男声、中英双语字幕，1080p竖屏成片及720p播放副本。两份最终MP4均通过完整解码与24fps恒定帧率检查，36个音频窗口通过比对，45张实际编码抽帧完成手机尺寸视觉复核。

这些结果属于已制作的案例。新人物必须重新核实事实、来源、字幕和最终文件；不能沿用旧片通过记录。未声称已在抖音或真实手机上完成播放测试，也不保证传播效果。

## 仓库内容

- `st-petersburg-math-documentary/SKILL.md`：触发范围与执行流程。
- `scripts/`：制作、配音、运行环境与冒烟验证脚本。
- `examples/`：通用项目配置示例。
- `references/`：叙事、手机排版、音频、验收和历史案例说明。
- `agents/openai.yaml`：显示名称与默认调用提示。
- `skill-package-manifest.json`：发布文件包的大小与SHA256清单。

后五项均位于 skill 目录内。本仓库不包含私人对话、账号信息、第三方视频、完整成片、依赖二进制或缓存。每次制作的素材权限和署名需要单独核查。
