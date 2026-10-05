# Git 协作规则与新人开发指南

适用项目：navi_minco_bit 导航仓库。版本：1.0。整理日期：2026-10-05。

对象：首次使用 Git 的开发者；Windows 编辑代码、Ubuntu/NUC 运行 ROS 项目；团队协作或两台设备同步。

阅读方法：第一次按 01-10 学习；部署看 11-12；排错看 13-18；日常使用查 21-22。PDF 支持目录跳转、书签与文本搜索。

本文是操作教学，不表示已执行提交、推送、合并或 NUC 部署。所有写操作由开发者按实际状态手动执行。代码中的“你的名字”“你的提交邮箱”需替换；带条件的命令不能整段盲目运行。

## 01 截图规则与当前项目：先选对分支

### 截图表达了什么

截图是团队约定：master 保存稳定版本，不允许开发者直接推送；develop 是工作分支，日常修改先在这里完成。修改经测试和负责人确认，再按团队流程进入稳定分支。截图没有展开最终合并步骤，不能认为推送 develop 后 master 会自动更新。

| 对象 | 截图中的项目 | 本导航仓库的本地核查 |
|---|---|---|
| 托管平台 | Gitee | GitHub |
| 稳定分支名称 | master | main |
| 开发分支 | develop | 本地当前未建立 develop |
| 本地文件夹 | 2027-sentry-navi | E:/RM学习/navi_minco_bit |
| 远程地址 | 截图给出的团队仓库 | wenhao-666-sys/navi_minco_bit |

### 本手册怎样使用这套规则

示例采用 main 保留集成版本、每项工作使用独立分支、经 Pull Request 合并。它是供新人采用的工作方式，不表示仓库已经开启分支保护，也不表示已经完成这些操作。若实际团队要求 develop，应以团队规则替换流程。

> 分支叫 master 并不会天然只读。限制来自团队规则、权限和平台保护。main/master/develop 也不是操作系统或 ROS 的设置。

核查日期为 2026-10-05：本地在 main，只有本地 main 与缓存的 origin/main；本次未执行 fetch，不据此断言服务器不存在其他分支。源码基线：6dba3a53bf20848ac92dc1fb0fdfdaf9e8376a44。

资料：[S04] 分支切换；[S11] 分支保护。案例依据：用户截图与本地只读检查。

## 02 Git 的四个位置：保存、暂存、提交、上传

### 四个位置各负责什么

Git 是版本管理工具；GitHub/Gitee 是托管平台。仓库不仅包含源码，还包含 .git 中的版本记录。复制普通文件和获得完整 Git 仓库不是同一种操作。

| 位置 | 含义 | 导航项目例子 |
|---|---|---|
| 工作区 | 正在编辑的文件 | 修改 ptp_sync.bash 后保存 |
| 暂存区 | 本次准备提交的内容 | git add 选定脚本修改 |
| 本地仓库 | 已提交的版本记录 | commit 保存一个版本 |
| 远程仓库 | 平台上的共享记录 | push 后供 NUC 下载 |

```text
工作区 -- add --> 暂存区 -- commit --> 本地仓库 -- push --> GitHub
                                                        |
                                               clone / pull
                                                        |
                                                   NUC 仓库
```

### 一个完整例子

你编辑脚本并保存后，仅工作区发生变化。add 把选中的修改放进暂存区；commit 以暂存内容建立记录；push 才把提交推送到远程。NUC 最后还要拉取。任何一步都不能由“我已经保存文件”替代。

> add 记录的是当时内容。add 后又编辑文件，需要再次 add 才能纳入后来修改。一个文件可能同时存在已暂存和未暂存的部分。

验收：能解释“commit 成功但 NUC 看不到”的原因，并指出缺少 push、拉取或分支选择中的哪一步。资料：[S03] 修改记录；[S05] add。

## 03 分支、HEAD 与远程分支

### 分支是版本路线

分支指向一条提交历史的当前位置。HEAD 通常表示你当前检出的分支或提交。新建分支不要求重新复制整个目录；切换会按目标版本更新文件。Git 可能为了保护未保存修改而拒绝切换，此时先处理修改，不能强制丢弃。

| 名称 | 含义 | 容易混淆的地方 |
|---|---|---|
| main | 本地主分支 | 可以落后于服务器 |
| docs/learning | 本地文档工作分支 | 斜线不是实体文件夹 |
| origin/main | 最近获取到的远程分支记录 | 不是实时读取服务器 |
| HEAD | 当前检出的位置 | 提交通常追加到当前分支 |

```bash
# 查看，不改变版本历史
git branch --show-current
git branch -a

# 条件操作：确认基点与现有修改后，创建工作分支
git switch -c docs/learning
```

命名示例：docs/git-guide、fix/imu-topic、feat/dual-port-ptp、perf/pointlio-batch。名称描述本次工作。一个分支尽量解决一个问题，避免把里程计优化、比赛策略和格式整理混成一项。

截图中的 git checkout develop 也是切换分支的写法；本手册优先使用含义更明确的 git switch develop。checkout 还有检出文件等其他用途，初学时不要混用这些形式。

### main 上没有某文件是正常现象吗

可能正常：文件仅提交在工作分支，还没合并进 main；也可能尚未提交或被忽略。先看分支、status 和历史，不要直接认定文件丢失。资料：[S04] switch；[S12] fetch。

## 04 origin、upstream 与你的仓库地址

### 名称与地址是两件事

origin 是远程仓库的常用别名，并非“必须是原作者”。clone 通常把下载来源命名为 origin。upstream 也只是可配置别名；本项目用它指向原作者。

| 别名 | 当前本地配置地址 | 用途 |
|---|---|---|
| origin | https://github.com/wenhao-666-sys/navi_minco_bit.git | 向自己的仓库共享修改 |
| upstream | https://github.com/Walker152/navi_minco_bit.git | 查看原作者更新 |

```bash
git remote -v
git branch -vv
```

第一条检查地址，fetch/push 行分别标明获取与推送地址；第二条查看本地分支及其跟踪关系。push 前需要同时确认远程和分支。能下载原作者仓库不代表有权向它推送。

> 本地命名为 upstream 的远程，与“分支的 upstream 跟踪关系”是不同概念。git push -u 中的 -u 设置分支跟踪关系，并不是选择名叫 upstream 的远程。

Windows 上的远程配置不会凭空出现在另一台电脑。NUC clone 自己的仓库后通常只有 origin；需要查看原作者更新时再按约定添加远程。当前只读检查没有验证账户权限或服务器最新状态。资料：[S02] 远程仓库；[S09] GitHub 认证。

## 05 首次准备：终端、作者信息与登录

### 选择正确的终端和目录

Windows 示例使用 PowerShell；NUC 示例使用 Ubuntu Bash。路径格式不同。两台电脑各自拥有本地仓库和配置。命令前的 # 是注释；本手册未添加 $ 或 PS 提示符，便于复制命令。

```powershell
cd "E:\RM学习\navi_minco_bit"
git --version
git config user.name
git config user.email
```

如果作者信息为空，替换以下值后手动设置。这里仅影响当前仓库；加 --global 才影响该用户其他仓库。

```powershell
git config user.name "你的名字"
git config user.email "你的提交邮箱"
```

### 作者信息不等于认证信息

name/email 写进提交作者记录，不会自动授予 GitHub 权限。首次 push 的登录认证另行处理。HTTPS 可使用凭据管理器或符合平台要求的令牌；SSH 使用密钥。GitHub 的 HTTPS Git 操作不接受账户登录密码。凭据无需写进代码或提交说明。

遇到登录失败先检查地址、账户、仓库访问权限及认证方式；不要反复改变分支或覆盖文件。这些动作解决不了身份问题。

完成标准：两台电脑都知道 Git 版本、仓库目录、作者设置和远程地址。安装 Git/ROS、建立 GitHub 权限与本次文档制作是不同操作。资料：[S06] config；[S09] 认证。

## 06 每次开工先看状态，再看差异

### 三个最常用的检查

```bash
git status --short --branch
git diff
git diff --cached
```

status 给出当前分支及文件状态。diff 默认查看已跟踪文件的未暂存差异；--cached 查看准备提交的内容。未跟踪的新文件不会像已跟踪文件一样直接出现在普通 git diff 中，需打开文件检查，或暂存后查看。

| 简略标记 | 含义 | 下一步 |
|---|---|---|
| ?? 文件 | 新文件尚未跟踪 | 检查后决定是否 add |
| 空格 M | 已跟踪文件被修改，未暂存 | 查看 git diff |
| M 空格 | 修改已暂存 | 查看 git diff --cached |
| A 空格 | 新文件已暂存 | 检查内容后提交 |
| MM | 同一文件暂存后又被修改 | 两部分分别检查 |
| UU | 存在未解决合并冲突 | 先处理冲突 |

### 工作区干净意味着什么

working tree clean 表示 Git 目前没有报告需提交的差异，不表示服务器已更新，也不证明程序正常。ahead/behind 是相对本地保存的远程记录；需要获取远程信息才能更新这个判断。

本项目文档最初出现 ?? learning/，说明这些新材料尚未进入版本记录。目录里存在不等于已经共享。资料：[S07] status；[S03] 修改记录；[S12] fetch。

## 07 首次下载与后续更新：clone / fetch / pull

### 首次在 NUC 下载自己的仓库

前提：NUC 能访问仓库、Git 可用、目标目录不存在或为空。已下载过时进入原目录，不要重复 clone 到非空目录。

```bash
git clone --branch main https://github.com/wenhao-666-sys/navi_minco_bit.git ~/navi_minco_bit
cd ~/navi_minco_bit
git status
git remote -v
```

| 命令 | 用途 | 是否整合到当前文件版本 |
|---|---|---|
| clone | 首次建立本地仓库 | 检出初始分支 |
| fetch | 获取提交和远程分支信息 | 不直接合并进工作分支 |
| pull | 获取并整合远程修改 | 按指定方式更新当前分支 |

### 已有仓库的更新

先确认当前在 main，待保存修改已处理，再执行更新。--ff-only 拒绝在历史分叉时自行合并；拒绝更新后查看第 17 章，不需要立即强制操作。

```bash
git branch --show-current
git status
# 满足上述条件后，手动更新
git pull --ff-only origin main
```

> git pull origin develop 不会替你切换分支；人在 main 上运行它，会尝试把那个远程分支整合到当前 main。团队使用 develop 时应先确认自己就在 develop。

资料：[S01] clone；[S08] pull；[S12] fetch。

## 08 第一次实操：把学习文档保存成提交

### 已有本地文档，先保存修改再更新基点

此例适合当前 Windows 仓库已有未跟踪 learning 文件的情况。先确认所在 main 和文件范围，在当前基点建立文档分支。不在这些文件尚未保存为提交时盲目切换、覆盖或拉取可能撞名的文件。

```powershell
cd "E:\RM学习\navi_minco_bit"
git status --short --branch
git branch --show-current
# 确认当前 main，且该工作分支名尚未使用
git switch -c docs/learning
git add learning/
git diff --cached --stat
git diff --cached
```

检查暂存清单后再保存版本。如果看到与本次无关的源码、设备数据或大量生成物，应先处理暂存范围，不要直接提交。

截图中的 git add . 里，点号表示当前目录；它会选择该目录范围内可纳入的新增、修改和删除。本例明确选择 learning/，方便你核对本次材料。

```powershell
git commit -m "docs: 添加导航学习和部署材料"
git status
git log -1 --oneline
git push -u origin docs/learning
```

### 每一步怎样知道成功

add 后：预期文件出现在暂存清单。commit 后：出现提交编号，status 不再报告已提交文件待提交。push 后：平台对应分支可查看该提交；若提示失败，不能当作上传完成。-u 建立跟踪关系，以后同一分支可简写 git push。

此分支不会自动进入 main。继续第 10 章的 PR；NUC 如果拉取 main，在合并前看不到工作分支上的文档。资料：[S03] 记录；[S05] add；[S02] 远程。

## 09 提交说明与分支命名规则

### 一个提交表达一项可理解的修改

格式采用“类型: 描述”，必要时写模块：fix(point_lio): 修正 IMU 订阅配置。类型是团队约定，不证明程序已验证。描述写具体结果，避免“更新”“修改了一些东西”。

| 前缀 | 用途 | 示例 |
|---|---|---|
| feat | 新增功能 | feat: 添加双网口同步入口 |
| fix | 修复问题 | fix: 修正 IMU 订阅话题 |
| docs | 修改文档 | docs: 补充雷达标定步骤 |
| style | 仅格式，不改逻辑 | style: 调整控制器缩进 |
| refactor | 重构实现结构 | refactor: 整理状态处理流程 |
| perf | 性能优化 | perf: 减少点云消息复制 |
| test | 添加或修改测试 | test: 覆盖帧配对边界 |
| chore | 工具与维护事项 | chore: 更新忽略规则 |

### 导航项目应在说明中补什么

较复杂修改在提交正文或 PR 说明里写触发条件、行为变化、验证方式与局限。例如改变 batch 参数，需要交代数据版本、耗时和精度对比，而不是仅写“优化里程计”。

一个提交不要混合双雷达接入、行为树策略、控制参数和格式清理。这样后续对比或撤销时能够准确定位。分支名按用途起：docs/git-guide、fix/imu-topic、perf/pointlio-batch。

资料：[S10] Conventional Commits。这些命名约定可经团队确定，并非现有仓库已自动强制执行。

## 10 Pull Request：让工作分支进入稳定版本

### PR 是提出合并修改的请求

本示例目标仓库是你自己的 wenhao-666-sys/navi_minco_bit。推送 docs/learning 后，在 GitHub 的 Pull requests 中创建请求，核对 base 和 compare。页面按钮与可用合并方式受权限及仓库规则影响。

| 项目 | 本例选择 | 含义 |
|---|---|---|
| 仓库 | 你自己的导航仓库 | 避免选到原作者仓库 |
| base | main | 修改要进入哪里 |
| compare | docs/learning | 修改来自哪里 |
| Files changed | 本次材料 | 逐项确认范围 |

创建步骤：选择来源分支；选择 Compare & pull request 或 New pull request；确认上述方向；填写标题和说明；查看文件变化；提交请求；满足审查和检查条件后合并。多人项目由团队授权的负责人处理合并。

### PR 说明模板

```text
问题/目的：新人缺少可查阅的 Git 指南。
改动：添加手册、学习入口和命令速查。
验证：检查文件、链接、PDF 与命令语法。
局限：没有执行 Git 推送或 NUC 实操。
```

合并后，工作区无待保存修改时，Windows 回 main 并更新。NUC 也需拉取，不会自动同步。

```bash
git switch main
git pull --ff-only origin main
```

资料：[S13] 创建 PR；[S14] 合并 PR。main 的“集成版本”用途不等于已经通过实车部署验证。

## 11 Windows 与 NUC 的日常同步

### 建议明确每台设备的职责

Windows 用于编辑与审查，GitHub 用于交换版本，NUC 用于运行与测量。NUC 若也修改代码，它就是第二个开发端，需要提交与共享这些修改，不能期待 Windows 自动知道。

| 操作位置 | 一次修改怎样流动 | 检查点 |
|---|---|---|
| Windows | 工作分支修改、提交、推送 | 文件范围、分支和远程 |
| GitHub | PR 审查后进入 main | 目标仓库、验证结果 |
| NUC | main 拉取后部署与验证 | 本地修改、依赖和配置 |
| NUC 有新修改 | 使用工作分支提交、推送、PR | 保存硬件修改与证据 |

NUC 更新之前先检查 status 和当前分支。雷达 IP、外参或串口修改尚未保存时，先按第 12 章处理。禁止把强制覆盖当成例行同步。

```bash
cd ~/navi_minco_bit
git status --short --branch
git branch --show-current
# 当前 main，待保存修改已处理之后
git pull --ff-only origin main
git rev-parse HEAD
```

### 怎样确认同一版本

两端更新到同一 main 后，比较完整提交编号，并分别检查 status。编号一致表示当前提交相同，不代表未提交修改相同，也不表示依赖、安装产物和硬件配置一致。

Git 同步源码及已跟踪文件；编译、系统服务、网卡 IP 与串口权限还需在 NUC 部署。不要将 Windows 的 build/install 当作 NUC 编译结果。资料：[S01] clone；[S08] pull；[S07] status。

## 12 NUC 的硬件配置与算法实验怎样保存

### 哪些事实必须和版本一起记录

双网口名称、雷达地址、同步方案、前后雷达身份、外参方向、串口设备、速度坐标约定都影响导航运行。只记录源码提交，不能完整复现设备实验。

| 记录项 | 例子 | 保存方式 |
|---|---|---|
| 代码 | 提交编号、工作分支 | 实验报告 |
| 参数 | 参数文件及实际加载入口 | 可共享配置与版本说明 |
| 硬件 | 网口、IP、安装与底盘 | 设备记录 |
| 环境 | Ubuntu、ROS、SDK、依赖 | 部署记录 |
| 数据 | bag 路径、时间、校验值 | 数据索引，不直接混入源码 |

### 避免两台设备争改同一个默认文件

团队可以设计示例配置和机器专用配置，但必须同时实现对应加载入口。本项目当前脚本仍有固定网口与目录，不能假定它已自动读取私有配置。若在 NUC 改了默认文件，就按真实修改保存并审查。

可选处理方式：对可共享修改建立配置分支，提交后 PR；对暂不共享的机器差异保留独立副本与说明，并明确启动时如何加载。不能只复制 YAML，却继续让 launch 读取旧文件。

> 配置文件、launch 覆盖、install 中的副本都可能影响实际运行。拉取源码成功不证明新参数已生效；按导航手册核对最终读取位置。

实验报告至少写：提交编号、参数差异、输入数据、设备配置、构建/启动来源、结果与回退决定。没有实测的结果标为未验证。本节为项目操作建议，依据已读启动脚本与配置入口。

## 13 团队协作：并行修改与冲突

### 两个人为什么会冲突

甲与乙从同一版本出发；甲提交并合并了新内容；乙基于旧版本也修改同一区域。整合时 Git 可能无法选择最终内容。不同文件有时可自动合并，但自动合并成功也不等于逻辑兼容。

例如两人同时修改同一个速度上限，冲突文件可能出现如下标记；这里用虚构文件演示，不是本项目真实参数：

```text
<<<<<<< HEAD
speed_limit: 1.0
=======
speed_limit: 2.0
>>>>>>> other-change
```

### 人工解决顺序

先停止继续提交或推送，查看 status，保存需要保留的内容。确认这是普通 merge 还是 rebase 等其他操作；上述“当前侧/另一侧”直觉只适合这里的普通合并示例。与相关开发者确认最终物理含义，编辑成正确内容，移除所有冲突标记，再检查配置与测试。

普通 merge 冲突解决后，需要暂存解决结果并完成合并提交；新手可请维护者协助。不要用“全接受我的”或“全接受对方的”代替对速度单位、坐标和外参的判断。

团队习惯：开工前更新基点；各自使用工作分支；一项改动一个 PR；参数变化写单位和验证依据；合并后共享版本编号。资料：[S15] merge。

## 14 修改暂存错了，或需要回退怎么办

### 先判断修改处于哪一层

| 当前情况 | 处理思路 | 会不会影响其他人 |
|---|---|---|
| 仅工作区修改 | 保存副本，检查差异后再决定 | 尚未共享 |
| add 了不该提交的文件 | 取消该文件暂存，保留工作区内容 | 尚未共享 |
| 已 commit 但未 push | 查看提交，决定追加修正或请维护者处理 | 尚未上传 |
| 已 push 或被别人使用 | 通常新增修正/撤销提交，走 PR | 需要团队协调 |

### 取消暂存：内容仍留在文件里

前提：仓库已有提交，且仅想把指定文件移出本次提交清单。

```bash
git restore --staged scripts/ptp_sync.bash
git status
```

--staged 针对暂存区；不要漏掉它。普通 git restore 指向工作区时可能丢弃未提交内容。先确认目标与状态，不在需要保留修改时直接使用。[S16]

### 已共享错误提交的回退

普通提交可通过 git revert 创建一个新的撤销提交，保留历史；需工作区干净，仍可能出现冲突，合并提交的撤销另有语义。新手先确认错误提交与依赖，再由维护者处理，不照抄一个编号执行。[S17]

本手册不将 reset --hard、clean -fd、强制推送列为日常恢复命令。源文件需要保留时，先做副本、查看 diff、记录状态。

## 15 .gitignore、地图、录包与文档

### 忽略规则只决定普通纳入行为

.gitignore 用于避免新文件意外进入版本管理，不会自动让已经跟踪的文件停止跟踪。修改忽略规则也不会删除历史中的数据。先检查文件是否已跟踪，再决定处理方式。[S18]

| 当前仓库已有规则 | 影响 |
|---|---|
| build/、install/、log/ | 这些目录中新文件通常不纳入 |
| *.png | 新 PNG 会被普通 add 忽略 |
| docs/ | 新审计记录不会自动进入提交 |
| *.csv、*.db、*.sqlite | 对应新数据文件被忽略 |

```bash
git check-ignore -v learning/assets/example.png
git ls-files learning/
git status --short --untracked-files=all
```

第一条的文件名为诊断示例，替换成实际路径；匹配规则时会显示来源。第二条查看已跟踪文件，第三条展开新文件清单。需要共享的文档和图片，应由团队调整规则或明确处理指定文件，而不是随意强制加入整个目录。

### 导航数据的存放边界

源码、必要配置、部署说明、可复现报告通常应管理。必要地图要依据大小、使用方式和团队规则决定，不能笼统排除所有地图。大体积 bag、PCAP、运行日志与中间结果放数据目录，提交索引、校验值和获取方式。

不要假定 bag 已被当前忽略规则覆盖；add 前查看暂存清单。不要把令牌、私钥或密码写进共享仓库。

## 16 Windows / Ubuntu 的路径、换行与脚本

### 复制命令时先核对终端

| 项目 | Windows PowerShell | Ubuntu Bash |
|---|---|---|
| 项目位置 | E:/RM学习/navi_minco_bit | ~/navi_minco_bit |
| 进入目录 | cd 加引号路径 | cd ~/navi_minco_bit |
| shell 脚本 | 本机不用于运行 ROS 部署脚本 | 用 Bash/对应解释器运行 |
| 编译产物 | Windows 本地环境的产物 | 在 NUC 环境中生成 |

CRLF 与 LF 换行差异可能造成大量无意义 diff，Bash 也可能因 CRLF 报错。可以先检查脚本换行，再由团队统一 .gitattributes 和编辑器规则；本手册没有修改现有规则。

```bash
git ls-files --eol scripts/ptp_sync.bash
git diff --stat
git diff --check
```

### 路径和加载入口仍需部署

start.bash 当前固定进入 ~/2027-sentry-navi，PTP 脚本固定网口 enp86s0。NUC 下载到 ~/navi_minco_bit 后不会自动修正这些值。依赖、网口、权限与可执行位问题应分别检查，不能因为 git pull 成功就直接启动整套实车链。

如出现脚本无法运行，先看解释器、换行、路径与权限，避免混成 Git 同步失败。资料：[S19] 属性与换行；[S20] diff。项目事实来源：start.bash、scripts/ptp_sync.bash。

## 17 常见报错：先诊断，再处理

| 提示/现象 | 常见含义 | 首先做什么 |
|---|---|---|
| not a git repository | 当前目录不在仓库内 | 检查终端位置，进入正确项目 |
| pathspec / invalid reference | 分支名错误或记录未获取 | branch -a；确认团队分支名 |
| destination path exists | clone 目标目录非空 | 确认是否已经下载，不删除原目录 |
| Author identity unknown | 没有作者信息 | 查看当前仓库 name/email |
| nothing to commit | 没有已选定修改可提交 | 查看 status、目录与忽略规则 |
| local changes would be overwritten | 更新可能覆盖本地修改 | 保存差异、提交或保留副本 |
| non-fast-forward / rejected | 远程已有本地没有的历史 | 获取后比较分叉，别立即 force |
| not possible to fast-forward | --ff-only 发现不能直接前进 | 核对当前分支与双方提交 |

### 分叉时的诊断命令

下面的 fetch 会访问远程并更新本地远程记录，不是修改源文件的合并操作；连接与权限需可用。其余命令用来查看历史。main 示例替换为实际工作分支。

```bash
git status --short --branch
git fetch origin
git log --oneline --graph --decorate -12
git log --oneline main..origin/main
git log --oneline origin/main..main
```

前一个范围列出远程有、本地 main 没有的提交；后一个反过来。两边都有时，说明需要决定整合方式；团队采用 merge/rebase 哪一种要按规则处理。资料：[S12] fetch；[S21] log。

## 18 常见疑问：上传、认证与版本对不上

| 疑问 | 可能原因 | 检查方法 |
|---|---|---|
| commit 成功，网页没变化 | 尚未 push，或网页看另一分支 | push 结果、分支下拉菜单 |
| 网页有文件，NUC 没有 | 未更新、不同分支或不同仓库 | remote、当前分支、提交号 |
| push 提示权限/认证失败 | 账户、凭据或访问权限不符 | 远程地址与认证方式 |
| Permission denied (publickey) | SSH 密钥未按平台配置 | 核对 SSH 身份与仓库权限 |
| 分支没有 upstream | 尚未建立跟踪关系 | 首次 push -u 后查看 branch -vv |
| 拉取后功能仍是旧的 | 实际运行安装副本/旧环境 | 核对工作空间与安装产物 |
| Git 编号一致，行为不同 | 本地差异、配置、依赖或硬件不同 | status、部署与实验记录 |

### 上传之后核对三件事

确认 push 返回成功；在自己的仓库选择正确分支；检查提交列表中的说明和编号。仅看到终端打印 commit 编号，不是上传证据。私有仓库的 NUC 下载也需要相应认证。

### NUC 运行之前核对三件事

实际目录与 remote 正确；当前分支和提交正确；实际加载配置与构建来源正确。Git 不同步系统安装状态，源码变化后可能需要重新编译；是否编译与怎么编译按工程要求另行执行。

本手册没有保存任何凭据，也没有验证 push、PR 或 NUC 实操成功。资料：[S02] 远程；[S09] 认证；[S07] status。

## 19 原作者更新怎样进入自己的导航仓库

### 不把 upstream 更新直接当作部署命令

自己的仓库用于共享本团队修改；原作者可能改变消息、参数、依赖和启动方式。先获取更新、审查差异，再在工作分支整合，测试后 PR。不要在实车稳定目录里直接整合未知改动。

```bash
# 前提：本机已配置名为 upstream 的远程
git remote -v
git fetch upstream
git branch -r
```

fetch 后查看原作者实际分支名，不假定也是 main。比较选定原作者分支与自己的版本，关注包依赖、话题、TF、时间单位、配置默认值、协议和控制输出；再决定是否接受。

| 阶段 | 产物 | 通过条件 |
|---|---|---|
| 获取与审查 | 更新摘要、差异清单 | 知道改了什么与影响谁 |
| 工作分支整合 | 可审查提交/PR | 本团队修改未误丢 |
| 验证 | 回放/仿真/实机报告 | 接口与行为满足要求 |
| 发布部署 | 已确认提交与配置 | 能回到上一可用版本 |

如 NUC clone 后没有 upstream，需要按团队规则另行配置；本手册未替你添加。替换里程计框架或更新控制协议应作为独立课题，不夹在例行 git pull 中。

资料：[S02] 远程；[S12] fetch。这里给出审查顺序，不提供未核验分支的自动合并命令。

## 20 新人练习与验收题

### 五个练习，逐步做完

| 编号 | 操作目标 | 应留下的证据 |
|---|---|---|
| G01 | 找到本地目录、分支和远程 | status、branch、remote 输出 |
| G02 | 创建工作分支并提交一份练习文档 | 分支名、暂存清单、提交号 |
| G03 | 推送并在网页找到同一提交 | 仓库/分支与网页编号 |
| G04 | PR 合并后在另一设备更新 | 两端提交号和 status |
| G05 | 解释一次被拒绝更新的原因 | 本地修改或分叉的诊断记录 |

练习前先确认权限和文件范围；G02-G04 会产生实际版本与远程变更，由你或团队手动执行。优先练习文档，不以真实底盘控制参数作为第一次 Git 练习。以上练习没有在本次制作中完成。

### 六个问题与参考答案

1. 保存文件后 NUC 能看到吗？不能，尚缺提交、推送及获取。
2. commit 成功是不是上传成功？不是，它先保存本地记录。
3. pull origin develop 会切换分支吗？不会，它整合到当前分支。
4. HEAD 相同是不是设备环境相同？不是，还要检查本地差异和部署。
5. origin 一定是原作者吗？不是，它只是别名。
6. master 天然不能修改吗？不是，限制来自团队规则与平台设置。

本次记录模板：日期、设备、目录、分支、remote、提交号、执行动作、实际结果、疑问、下一步。用真实输出记录，不把示例当作已完成证据。

## 21 命令速查：查看与诊断

| 目的 | 命令 | 解释 |
|---|---|---|
| 看版本 | git --version | 本机 Git 版本 |
| 看状态 | git status --short --branch | 分支与待处理文件 |
| 看当前分支 | git branch --show-current | 当前分支名称 |
| 看全部记录分支 | git branch -a | 本地及缓存远程分支 |
| 看远程地址 | git remote -v | 获取/推送地址 |
| 看跟踪关系 | git branch -vv | 本地分支及远程关系 |
| 看未暂存修改 | git diff | 不包含普通未跟踪新文件内容 |
| 看本次暂存 | git diff --cached | 即将提交的内容 |
| 看修改量 | git diff --cached --stat | 暂存文件与变化统计 |
| 看最近提交 | git log -5 --oneline | 最近五个记录 |
| 看版本全号 | git rev-parse HEAD | 当前完整提交编号 |
| 看某次修改 | git show 提交号 | 替换为真实编号 |
| 查忽略原因 | git check-ignore -v 路径 | 替换为真实文件路径 |
| 看跟踪文件 | git ls-files | Git 已管理的文件 |

这里的命令用于查看，不修改源码或历史。它们只能报告相应版本状态，不会验证导航性能、同步精度或硬件安全。

日常优先顺序：目录 -> remote -> 分支 -> status -> diff -> 暂存清单 -> 提交号 -> 远程结果 -> NUC 实际运行来源。资料：[S07] status；[S20] diff；[S21] log。

## 22 命令速查：手动开发与发布清单

| 动作 | 命令示例 | 前置条件 |
|---|---|---|
| 首次下载 | git clone 地址 目录 | 替换地址，目标目录空 |
| 获取更新记录 | git fetch origin | 地址、网络与权限可用 |
| 创建工作分支 | git switch -c docs/git-guide | 基点正确，名称未占用 |
| 选择修改 | git add learning/ | 确认范围与忽略文件 |
| 移出暂存 | git restore --staged 路径 | 替换路径，保留文件内容 |
| 保存本地版本 | git commit -m "docs: 添加指南" | 暂存已审查，作者已设置 |
| 首次共享分支 | git push -u origin docs/git-guide | 地址、分支、权限正确 |
| 更新 main | git pull --ff-only origin main | 当前 main，修改已处理 |

### 开工、提交、合并、部署四张检查单

开工：确认目录和 remote；看当前分支和修改；处理上次工作；更新正确基点；建立本次工作分支。

提交：检查 diff；仅选有关文件；核对暂存内容、单位与路径；使用具体说明；保存提交号；推送后核对网页。

合并：PR 目标仓库和 base 正确；改动范围清楚；验证依据可复现；未验证内容明确；团队规则满足；双方更新 main。

部署：保存 NUC 本地修改；核对版本和配置；按工程要求构建；分模块检查输入、时间、TF 与输出；记录结果和回退依据。

> 本仓库 AGENTS.md 禁止 Agent 执行 Git 提交类写操作，并要求构建先得到明确许可。手册中的命令供开发者学习和手动操作；本次仅制作文档，不执行这些开发/发布动作。

## 23 官方资料与术语索引

### 官方资料：按编号回查

| 编号 | 文档名称 | 链接 |
|---|---|---|
| S01 | Git clone | https://git-scm.com/docs/git-clone |
| S02 | Git 远程仓库 | https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes |
| S03 | Git 修改记录 | https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository |
| S04 | Git switch | https://git-scm.com/docs/git-switch |
| S05 | Git add | https://git-scm.com/docs/git-add |
| S06 | Git config | https://git-scm.com/docs/git-config |
| S07 | Git status | https://git-scm.com/docs/git-status |
| S08 | Git pull | https://git-scm.com/docs/git-pull |
| S09 | GitHub 远程与认证 | https://docs.github.com/en/get-started/git-basics/about-remote-repositories |
| S10 | Conventional Commits | https://www.conventionalcommits.org/en/v1.0.0/ |
| S11 | GitHub 分支保护 | https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches |
| S12 | Git fetch | https://git-scm.com/docs/git-fetch |
| S13 | GitHub 创建 PR | https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request |
| S14 | GitHub 合并 PR | https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request |
| S15 | Git merge | https://git-scm.com/docs/git-merge |
| S16 | Git restore | https://git-scm.com/docs/git-restore |
| S17 | Git revert | https://git-scm.com/docs/git-revert |
| S18 | Git ignore | https://git-scm.com/docs/gitignore |
| S19 | Git attributes | https://git-scm.com/docs/gitattributes |
| S20 | Git diff | https://git-scm.com/docs/git-diff |
| S21 | Git log | https://git-scm.com/docs/git-log |

术语回查：仓库/工作区/暂存区/commit/push 看 02；branch/HEAD/origin/main 看 03；origin/upstream 看 04；clone/fetch/pull 看 07；PR 看 10；冲突看 13；忽略规则看 15。

资料核对与本地检查日期：2026-10-05。在线页面会更新，实际行为还应结合本机 Git 版本与团队规则。当前 Windows Git：2.55.0.windows.5。全文采用自己的解释和项目例子，不复制官方长篇内容。

未执行构建：AGENTS.md 禁止在未获用户明确许可前运行构建命令。
