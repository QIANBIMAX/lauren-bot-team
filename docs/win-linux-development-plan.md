# Windows / Linux 开发与发布计划

交付对象：Grok Bot 指挥官及开发团队。日期：2026-11-05（Asia/Shanghai）。代码基线：`f0d1734`。

本轮目标是 lauren-bot-team 的 Lite 与 Team **原生** Windows/Linux 支持；不是开发 VibeX 的 Windows/Linux 版本。VibeX 适配、Full 实现暂缓，已有调研材料保留（本仓 `f0d1734` 没有名为 VibeX 的文档，本次不删任何既有材料）。本文是待实施计划，不表示目标平台已经验收。

指挥官已定补丁写在 **第六节执行顺序**、**第七节非目标**、**第八节真机归属**。下文其余部分沿用 2026-11-05 草案，并按这些补丁改过顺序和边界。

## 一、产品范围与发布边界

- Lite 三角色、Team 七角色保持平行独立；跨平台复用同一 kit，不复制业务代码维护两套分支。
- 首发目标：Windows 11 x64 原生环境、Ubuntu 24.04 LTS x64；macOS 保持回归。Windows ARM、其他发行版、WSL、容器和服务器常驻服务作为后续独立支持项。
- 建议首发主测 Python 3.12，保留项目声明的 Python 3.11 最低版本兼容测试；不凭主测版本通过就宣布所有未来版本可用。
- Windows 默认不要求 WSL、Git Bash、管理员权限；Linux 默认不改系统 Python、不要求 root 运行项目。
- 不 fork OMB。先完成 kit/CLI/Demo 原生支持，再分别核实 OMB 对目标平台的发行物、引擎与导入能力。
- 当前 `omb_delegate` 仍未接通真实平台委派。跨平台计划不能把这个平台能力缺口默认为已解决。真实委派接线是**单独事项**，不能用终端模拟替代，也不能在 kit 预览里写成已经可用。

发布分成两个可独立说明的范围。原生 kit 预览（W0–W6）先于 OMB 工作台（W7）：

| 范围 | 必须交付 | 不能据此宣称 |
|---|---|---|
| 原生 kit 预览 | 安装、CLI、实际 Git/验收程序、规则探针、预算恢复、Lite/Team 协议演示 | OMB 已真实导入、真实多助手已跑通、`omb_delegate` 已接通 |
| 工作台完整支持 | 以上全部 + 对应 OMB 发行版、模型引擎、导入、实际委派、应用重启与失败恢复 | 其他未测试的系统/架构/引擎自动兼容 |

如果 OMB 某平台无可用发行版，先发布该平台原生 kit 预览并明确限制；不临时改用 VibeX 并沿用同一验收结论。

## 二、代码基线与已知缺口

基线 `f0d1734` 已有真实 worktree、权限矩阵、Team handoff、Nancy 持久待办、预算恢复门、原子写入、租约及对账。最近 macOS kit 测试基线为 128 项通过；这不是 Windows/Linux 证据。

下表是基线缺口，不是“已经做完”的清单。第一个实现切片只处理 W0 诊断骨架，以及 W2 中会在 Windows 上误伤进程的探活；其余行仍待后续 PR。

| 模块 | 当前问题 | 目标改动 |
|---|---|---|
| atomic_io.py | fcntl 缺失时无跨进程锁；仅原子替换不保证读改写无丢失 | 跨平台有效锁或单写入事务；锁覆盖完整读改写 |
| runtime.py | 用 os.kill(pid, 0) 探活，SIGTERM 取消；与 Windows 语义不兼容 | 分平台进程探活、身份核对、退出确认和受控子进程管理 |
| rule_check.py | 只从 Markdown Bash 块解析并执行 bash -c；固定 .venv/bin/python | 原生 Python/argv 探针，Bash 仅显式可选 |
| protocol.py | 默认验收命令包含 cd、&&、.venv/bin/python | 结构化 argv/cwd/env/timeout，旧命令显式兼容 |
| scripts / Demo | C/T 系列大多 Bash、POSIX 路径与 shell 环境写法 | 一个 Python 场景实现，PowerShell/sh 仅薄入口 |
| worktree / merge | 路径、大小写、Git 配置、文件占用、共享仓库锁差异 | 统一路径身份、文件系统诊断、共同 Git 仓库级集成锁 |
| pyproject / 安装 | 主要 editable 开发安装；运行期 Schema 为可选依赖 | 用户安装依赖完整、wheel 干净安装验证 |
| docs / CI | Mac 为主；Win/Linux 未验收，未发现现成 workflow | 原生 CI、平台手册、真实机器和 OMB 验收 |

最高优先级问题：Python 官方说明 Windows 的 os.kill 对 CTRL_C/CTRL_BREAK 以外的信号值采用 TerminateProcess。因此不能把 POSIX 的 os.kill(pid, 0) 探活逻辑直接带到 Windows，更不能先在真实用户进程上试验。先以平台判断隔离，再使用可牺牲测试进程验证替代实现。

依据：[Python 3.12 os.kill 文档](https://docs.python.org/3.12/library/os.html#os.kill)。

探活选型（第一个切片已定，只用标准库）：

- POSIX 保持 `os.kill(pid, 0)`。
- Windows 使用 `ctypes` 调用 `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`（`0x1000`，查询权限，不含 `PROCESS_TERMINATE`），读到结果后 `CloseHandle`。不调用 `os.kill`。
- 不引入 psutil。创建时间能读到时，用它区分 PID 重用；读不到则返回未知，不把未知当成“可以杀”。
- Windows 取消只写协议层 `cancel_requested`，状态为 `windows_incomplete`。Job Object / 受控进程树留到 W2 余量，不能写成已经会停掉子进程。

## 三、架构原则

业务层保持任务、权限、验收、合并、预算、规则语义一致；平台差异集中在以下适配点：

1. 环境与解释器发现。
2. 命令运行与输出编码。
3. 进程身份、探活、取消与对账。
4. 文件锁、原子替换、路径与文件系统能力。
5. Git 能力与工作区生命周期。

不要在每个业务函数散布 shell 判断。现有模块逐项改造，新增模块名由实施时确定。版本号属于发行/协议元数据，产品线展示名和目录继续无版本后缀。

## 四、详细开发任务

### W0：环境基线与可重现诊断

建立 Windows 11 x64 与 Ubuntu 24.04 x64 的干净环境记录，固定主测 Python/Git/OMB/引擎版本。Win 可使用真实机或原生虚拟机；Linux 首轮 CLI 可用 VM，桌面工作台验收必须有桌面会话。

实现统一 doctor 诊断：系统/架构、解释器、Python 包、Git 与 merge-tree 能力、可写目录、锁、子进程、UTF-8、长路径、可选 Bash、引擎与工作台状态。提供机器可读结果与简短解决提示。

不输出 Key/账号原文；不自动写全局 Git 配置、改执行策略、关闭 TLS 校验或申请管理员权限。缺依赖提示用户按平台安装。网络代理/镜像可由用户显式配置，不内置个人代理。

退出：两平台有可归档环境清单；doctor 能准确区分必需缺失、可选缺失和未实测工作台。

第一个切片只交付 doctor 命令与当前环境测试，**没有**两平台归档环境清单，因此不关闭本项。

### W1：跨平台命令与验收契约

扩展验收描述，推荐 exec 类型使用 argv 数组、cwd、env、timeout；Python 命令从实际解释器解析，不能写死 python3 或 .venv/bin。环境变量通过 subprocess 的 env 传递，切目录通过 cwd，不拼成 shell 字符串。

旧 command 字符串保留兼容与明确执行类型：POSIX shell 命令只在能力满足时运行；Windows 原生场景不能偷偷落入 Git Bash。含 shell 运算符的旧记录不做猜测式拆词转换。

提供统一返回：启动失败、正常退出、非零退出、超时、取消、无法判定；保存真实 argv/cwd、解释器、时间、退出结果及 stdout/stderr。命令参数按字段脱敏，不丢失原始错误。

一次验收先创建 round，全部检查写入同轮再汇总；新 SHA/验收定义变更使旧报告失效。新增字段先更新权威 Schema，兼容副本同步，文档 JSON 示例可验证。

退出：中文/空格路径、含特殊字符参数、空参数、非零退出与超时在两平台行为明确；至少两项 must_run 同轮通过，缺一项不通过。依据：[subprocess 官方接口](https://docs.python.org/3.12/library/subprocess.html)。

### W2：Windows 进程与取消恢复（发布阻断项）

移除 Windows 对 os.kill(pid, 0) 的调用，新增无副作用探活实现。可选使用成熟跨平台进程库或 Windows 原生查询，选型后明确依赖和最小权限；不能依赖信号试探进程是否存活。本切片选定标准库 `ctypes` / `OpenProcess` 查询，见第二节。

为项目启动的进程记录 PID、创建时间、执行 ID、受控工作区、父进程/进程组或 Windows Job Object 等身份信息；PID 相同但创建时间不同，不得认为是原任务，避免 PID 重用后误杀。创建时间比较已有辅助函数；租约里持久记下创建时间、以及 Windows Job Object 取消，仍是本项余量。

取消顺序：标记取消请求→通过执行器或受控进程机制请求停止→等待退出→必要时按策略强制结束受控进程树→确认结果。POSIX 使用受控进程组；Windows 选择可验证的进程树管理方式。不能按进程名清理所有 Python/模型进程，不能杀共享助手引擎。

只有确认停止才能记录停止成功；权限不足或状态未知保持受阻。重启对账同时检查进程身份、Git 状态、产物和历史回执；取消不代表外部操作或代码自动回滚。

退出：牺牲子进程探活不会退出；取消能停止目标及受控子进程而不影响旁路进程；PID 重用、权限不足、重复取消、程序重启均有反例测试。涉及真实进程的测试先用隔离测试子进程，不用用户工作进程。

第一个切片做到：牺牲子进程探活不死、缺失 PID / 创建时间不一致不当成同一执行器、Windows 路径不调用 `os.kill`、Windows 取消标明未完成。还没有“取消能停掉整个受控子进程树”的实现，该项退出条件因此未满足。

### W3：跨进程锁与 Git/路径（发布阻断项）

Windows 不允许锁降级成 no-op。文件锁覆盖 load→校验修订→修改→保存；多个独立进程更新同任务不丢记录。task/team/handoff 多文件更新提供可恢复提交标识和对账策略，不能把多个原子文件当整体事务。

原子替换增加文件占用/权限错误的有界重试与明确失败；失败不得截断原文件。优先支持本地 NTFS/ext4，网络盘、同步盘先标未支持/未测；不对所有文件系统承诺相同一致性。

集成锁按 Git common-dir 的规范身份和目标分支共享，避免不同 worktree 各拿一把锁。实际合并队列串行；不通过删除锁文件强行抢占正在运行的合并。

路径用 pathlib，覆盖盘符、反斜杠、大小写、..、符号链接/junction、Windows 保留名与非法字符、尾随空格/点。外部 task 标识映射为稳定目录 ID，业务标题保留中文；重名或大小写碰撞报错，不覆盖任务。

Git 诊断记录版本、autocrlf、safe.directory、merge-tree 支持，不全局修改配置、不用 safe.directory=*。用仓库级 .gitattributes 约定源文件/脚本换行；验证内容摘要在 CRLF/LF 下的定义。遇到路径过长给出可操作建议，不强行改变系统策略。

退出：多进程竞争、锁超时、进程异常退出、文件占用、不同 worktree 同目标合并均通过；退出后可清理自身 worktree，无误删用户分支。

### W4：规则探针与 Demo 原生化

rule_check 新增结构化探针入口，默认 Python/argv，在 Win 无 Bash 环境运行。现有 Markdown Bash 规则明确声明 requires_bash；不支持时返回无法执行而非 pass。逐项迁移公开内置规则及 lessons 样例，保留历史文件和证据。

将 C1 正常、C2 失败修复、C3 规则复用、C6 恢复、C7 预算、C8 规则发布，以及 Team T1～T4 的必要逻辑放入 Python 场景运行器。原 .sh 可保留为薄包装，Windows 入口只调用同一实现；不要复制两份大型场景脚本。

每次新 run 使用唯一目录与真实 Git commit，默认不 --force 覆盖用户 Demo。修复轮绑定新验收，发布规则后正反样例与加载回执完整；使用进程参数传路径，不把含特殊字符的路径塞进 python -c 字符串。

退出：Windows 无 WSL/Git Bash 跑通；Ubuntu 原生跑通；成功/失败/修复/发布结果都可重放；历史脚本各自标明兼容范围，不虚构 Linux 已通过。

### W5：Lite 与 Team 集成回归

Lite：真实工作区→开发产物→独立验收程序→默认 confirm→本地集成→后置检查→完成；覆盖 fail、inconclusive、旧 SHA、缺日志、拒绝确认、already_merged、冲突、预算恢复。

Team：默认工程链、A/B 各自接单、依赖与归属、重试与返工、Nancy 待办/汇总/阻塞解除、规则交接；至少两个独立进程产生重叠活动并验证状态更新不丢失。无模型的程序场景可以验证协议并发，但不记作真实助手并发。

所有权限和验收检查与 macOS 一致，不为 Windows/Linux 放宽。平台 API 仍未接通时模式明确 local/simulated/blocked，不将“任务状态已写入”当作真实委派。

退出：两产品线各自独立、互不要求先部署另一条；三平台原有门禁回归，新平台新增反例通过。

### W6：安装、打包与新人文档

先交付 Python wheel/sdist 与完整依赖安装，不做无必要的 exe/AppImage 封装。若 OMB 自身需安装器，直接使用其官方对应发行物，记录校验信息，不重打包冒充自研客户端。

用户正式安装包含必需 Schema 校验依赖，开发依赖独立；验证 wheel 在源码目录外可运行，规则/Schema 等运行资源确实随包提供。安装后命令不依赖开发机 editable 路径。

提供 bootstrap.ps1、bootstrap.sh 薄入口及逐条手工命令。Windows 使用 py/python 与 .venv/Scripts，Linux 使用 python3 与 venv；PowerShell 脚本受策略阻止时提供直接 Python 命令，不永久设置 unrestricted/bypass。脚本只操作项目目录，不覆盖现有 venv 或用户配置。

文档分 Windows、Ubuntu、公共使用/恢复三部分，覆盖模型/引擎配置、权限、网络、中文路径、依赖缺失、Git 未配置、锁占用和进程未知。模型 Key 由用户填一次，不要求贴入对话。

退出：全新普通用户环境照文档完成 kit 首个 Demo，错误提示能定位问题；公开材料无真实 Key、账号和个人路径。

### W7：OMB 桌面与真实引擎验收

开工先核对 OMB Windows/Linux 官方发行物与安装方式；macOS 版本钉死信息不可直接复制。为每个平台固定实际引擎版本和认证方式；未找到官方支持时报告具体阻塞。

分别导入 Lite 和 Team：角色、职责、权限、工作目录和配置完整；重启保留信息；真实任务委派、验收和失败恢复有独立证据。单助手轮流扮演角色不算独立验收。

本轮若只完成 W0～W6，发布“原生 kit 预览”，W7 保持未验收。若要完成 W7，现有 `omb_delegate` 恒 blocked 的桥接缺口须另列工作任务，明确可调用接口/回执与可信身份后实施，不估作简单点击导入。W7 排在原生 kit 预览之后，不与本切片混做。

## 五、CI 与测试矩阵

建议新增 `.github/workflows/cross-platform.yml`：使用固定映像标签，Windows runner、ubuntu-24.04、macOS 回归，Python 3.11/3.12。runner 标签实施时核对；Windows Server CI 结果不能等同 Windows 11 桌面/OMB 验收。

每个 job 的目标顺序：干净安装→Schema/包自检→kit/Demo pytest→原生场景→wheel 安装验证→归档脱敏报告。PR CI 不使用模型 Key/个人登录；真实引擎/GUI 为受控集成测试，独立记录。

不能为了通过而 skip 所有 Windows 锁、进程、规则、合并测试。仅对确属平台专用机制分组，用另一平台的等价行为测试替代。故障产物即使测试失败也归档，限制保留范围与敏感内容。

第一个 PR 只落地骨架，不把上面的完整顺序说成已经在跑：

- 矩阵：`windows-latest`、`ubuntu-24.04`、`macos-latest` × Python 3.11 与 3.12，`fail-fast: false`。
- 每个 job：干净安装 → 把已提交的 demo fixture 种到 gitignore 的 `demo-app/data/tasks.json`（现有 Bash 规则探针在干净检出上否则会缺文件；这不是 Demo 原生化）→ `lauren-team-kit` 的 pytest（含 doctor 与 runtime 探活；不为这些新测试加整组 skip）→ 注明完整 Demo Bash 场景仍可能只在 Mac/Linux。
- wheel、原生场景、脱敏归档留在后续。`windows-latest` 不是 Windows 11 桌面验收。

测试重点（随对应任务补齐，不在第一个切片全部变成已测）：

- UTF-8/中文/空格/特殊字符、stdout/stderr、CRLF/LF、大小写冲突与路径穿越。
- 真实互斥锁、完整读改写、异常退出后锁恢复、文件占用与替换失败。
- 无副作用探活、取消整个受控任务树、不影响旁路进程、PID 身份与重启。
- worktree/Git 冲突、分支占用、幂等合并、合并后检查失败、不同工作区共用锁。
- Lite 失败修复、同轮多检查、预算耗尽后恢复拦截；Team 并发写入、归属与 Nancy。
- 无 Bash Windows、无预装开发工具的用户环境；Ubuntu 显式安装缺失的 venv/Git。

参考：[GitHub 托管运行器说明](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)。

## 六、执行顺序、交付与验收门

单线推进，不并行铺开整条 W1/W2/W3：

1. **W0** doctor 骨架（本 PR）。
2. **W2 探活隔离**（同一 PR，安全阻断）：Windows 不得再调用 `os.kill(pid, 0)`。Job Object 取消树、租约持久身份不在本 PR 做完。
3. 后续 PR，仍是一条流：**W3 锁** → **W1 命令契约** → **W4 Demo** → **W5** → **W6**。
4. **W7 工作台**放在原生 kit 预览（W0–W6）之后。发行物可行性可以另记笔记，但不把 GUI 接线提前塞进本 PR。

本 PR **不实现**完整的 W1、W3、W4、W5、W6、W7，也不把 `omb_delegate` 接上真实平台。

依赖：优先标准库。本切片不新增第三方包，`pyproject.toml` 的依赖列表保持为空。若后续 PR 要加入 psutil、portalocker 或其他库，必须在该 PR 说明理由，并显式写入 `pyproject.toml`，不能只在环境里临时安装。

| 里程碑 | 交付 | 通过条件 |
|---|---|---|
| M0 环境与范围冻结 | 平台清单、doctor、OMB 可行性、CI 骨架 | 知道哪些平台实际可测，Windows 无危险 POSIX 探活路径 |
| M1 平台底座 | 命令、进程、锁、路径与 Git | 两平台原生反例通过、macOS 无回归 |
| M2 程序闭环 | Python 场景、规则探针、Lite/Team 测试 | 无 Bash Windows 与 Ubuntu 实际完整运行，未跳过关键能力 |
| M3 新人预览发布 | wheel、引导脚本、手册、脱敏报告 | 新环境可重复安装；预览限制写清 |
| M4 工作台发布 | 两平台 OMB/引擎/导入/委派证据 | 真实工作台闭环、失败恢复、重启均验收 |

本 PR 不关闭 M0：没有两平台可归档环境清单，也没有 OMB 可行性结论。它只提供 doctor、CI 骨架，以及“Windows 探活不再走 `os.kill(pid, 0)`”。

先按验收门推进，不承诺缺少真实机器与模型接口时的固定完成日期。估时应拆为实际编码、CI、真实机器测试和平台阻塞；报告已实现 / 自动测试 / 真实机 / GUI 分列，不能用代码百分比覆盖平台验证。

最终交付包括平台适配模块、依赖与契约迁移、CI、原生演示、安装包、Windows/Ubuntu 文档、真实进程恢复报告、Lite/Team 兼容矩阵和已知限制。更新 README/STATUS/platforms/compatibility/release checklist 的状态必须有对应证据；禁止提前将 `platforms: any` 当作发布结论。

## 七、首个派发任务与非目标

第一个派发按第六节的单线执行：冻结 Python/系统基线的诊断入口、创建三平台 CI 骨架、隔离 Windows `os.kill` 探活。跨平台锁、结构化命令与规则探针、真实闭环留在后面的 PR。每项提供输入、可改范围、验收命令、输出证据、回滚方式；底层共享改动同时覆盖 Lite/Team，不各写一套。

### 非目标

本线不做：

- VibeX 适配。已有调研材料保留作延后材料，不删除，也不在本线改写成 Win/Linux 交付。
- Full 角色与 Full 产品线。
- 国内消息平台扩展、长期后台守护、所有 Linux 发行版、Windows ARM、跨机运行、同步盘/网络盘一致性保证。
- 第一个 PR 另外明确不做：完整跨平台文件锁、argv / 验收命令契约迁移、Demo Python 化、OMB 导入、完整 OMB GUI 接线、`omb_delegate` 真实桥接。

`omb_delegate` 今天仍是 blocked / simulated。文档和 doctor 必须写成未接通、未探测，不能用“任务状态已写入”或终端模拟代替真实委派。

保留相关扩展接口，不以这些外围工作阻塞原生平台支持。计划文本本身不代表已经跑过 Windows/Linux 真机。

## 八、真机归属

| 事项 | 谁做 | 本 PR |
|---|---|---|
| kit 代码、doctor、探活隔离、单元测试、GitHub Actions 骨架 | 实现侧，在本仓库提交 | 做 |
| Windows 11 x64 / Ubuntu 24.04 x64 桌面上的 OMB GUI：导入、真实委派、重启、失败恢复 | 人工在有桌面会话的环境后续验收 | 不做 |
| `omb_delegate` 真实桥接 | 单独事项，先有可调用接口、回执和可信身份 | 不做，也不写成已通 |
| `windows-latest` 与 Ubuntu CI 上的 pytest | 自动测试证据，只覆盖跑到的用例 | 骨架会跑；不能代替上两行 |

Linux 上能跑的 CLI 测试，不能写成 Ubuntu 桌面工作台已验收。Windows runner 是托管 Windows 环境，不能写成 Windows 11 桌面已验收。没有对应证据时，`docs/platforms.md` 保持未测，禁止改称 `platforms: any` 已支持。
