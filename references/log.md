# 细碎经验账本

编号只增不改；每条都来自真实操作。搜关键词比按分类找更快。

> **追加条目前，先取全局最大编号，别凭印象。** 多人／多 agent 并行时，
> 你看到的"最新编号"可能别人还没提交；直接 +1 会撞号（已经发生过两次）。
>
> ```bash
> grep -oE "^### E-[0-9]+" references/log.md | sort -V | tail -1
> ```
>
> 取到的数字 +1 才是安全的新编号；追加完再跑一次 `uniq -d` 自检：
> `grep -oE "^### E-[0-9]+" references/log.md | sort | uniq -d`（输出为空才算通过）。

## shell / 脚本

### E-001 命令替换里的变量赋值传不出来

- 场景：`BODY="$(call_api ...)"`，而 `call_api` 内部想顺手设置 `STATUS=200`。
- 现象：函数里赋值看似成功，外面读 `$STATUS` 却报 `unbound variable`（开了 `set -u` 时直接退出）。
- 根因：`$( )` 会开**子 shell**，函数体在子进程里执行，变量不会回流到父 shell。
- 修法：需要回传"第二个值"时走文件或进程替换：
  ```bash
  call() { local raw; raw="$(curl -sS ... -w '\n%{http_code}')"
           printf '%s' "${raw##*$'\n'}" > "$TMP/status"
           printf '%s' "${raw%$'\n'*}" }
  status() { cat "$TMP/status"; }
  ```
- 教训：shell 里"函数返回多个值"没有原生语法；要么 echo 两行再 split，要么走临时文件，别指望变量。

### E-002 用 `head` / `test` 当函数名会把命令遮住

- 场景：脚本里定义 `head()` 打印分节标题，脚本里后来又用了 `head -n 5 file`。
- 现象：函数优先于外部命令，`head -n` 行为诡异或直接报参数错误。
- 根因：bash 函数名与外部命令同一命名空间（且函数优先级更高）。
- 修法：起名避开常用命令：`section()`、`divider()`、`log_head()`。
- 教训：脚本里的工具函数不要撞 `head` / `test` / `ls` / `rm` / `kill` / `time` 这些高频命令。

### E-003 `source .env` 遇到未加引号的尖括号会炸

- 场景：`set -a && source .env && set +a`，而 `.env` 里写着 `SMTP_FROM=课程站 <no-reply@x.com>`。
- 现象：`syntax error near unexpected token 'newline'`，脚本连第一行都没跑起来。
- 根因：`source` 执行的是 **shell 语法**，不是 dotenv 解析；`<` 被当成重定向。
- 修法：解析前把含特殊字符的值加引号（`sed -E 's/^([A-Z_]+)=(.*[<> ].*)$/\1="\2"/' .env > /tmp/x.env`），或用语言自带的 dotenv 解析器加载。
- 教训：`.env` 是"给程序读的"，不是保证"给 shell 读的"；能用进程自带的 dotenv 就别 `source`。

## build / deploy

### E-010 覆盖式解包不会删除旧文件

- 场景：`tar czf - . | ssh host 'tar xzf - -C /opt/app'` 这种"传过去覆盖"的部署方式。
- 现象：本地删掉/重命名过的源码在服务器上仍然存在，参与编译后报重复声明（`other declaration of X`）或编译不存在的旧接口。
- 根因：`tar x` 只覆盖同名文件，**不会同步删除**。
- 修法：解包前先删掉"归档全量拥有"的目录，例如 `ssh host "rm -rf /opt/app/apps"`；或改用 `rsync -a --delete`。
- 教训：**覆盖式部署必须显式清理**。要么删目录，要么用 rsync 的 `--delete`，别指望 tar。

### E-011 外网验收查 IP 会被 HTTPS 跳转骗

- 场景：部署脚本用 `curl http://<IP>/` 判断服务是否正常。
- 现象：永远是 301/308，脚本报"验收未通过，检查防火墙"，但站点其实是好的。
- 根因：网关（Caddy/Nginx）把 HTTP 统一 301 到域名 HTTPS，IP 不是最终落点。
- 修法：验收直接打真实域名并且跟随跳转：`curl -sL -o /dev/null -w '%{http_code}' https://<domain>/path`。
- 教训：健康检查要打**用户实际访问的入口**（域名 + HTTPS），不要打中间形态（IP + HTTP）。

### E-012 构建容器里 `go build` 报私有模块拉不下来

- 场景：私有 Go module（如 `github.com/<org>/<kit>`）作为依赖，在服务器上构建镜像。
- 现象：`fatal: could not read Username for 'https://github.com'`（或 403）。
- 根因：构建环境没有凭据，且 Go 默认走 proxy/sumdb，对私有库不适用。
- 修法：`GOPRIVATE=github.com/<org>/*` + 构建前把只读 token 写进容器可见的 `~/.netrc` 或 `git config url.insteadOf`；token 只放在服务器 `0600` 文件里，不进仓库、不进镜像层。
- 教训：私有依赖的**凭据注入要设计进部署流程**，别指望"本地能构建 = 服务器能构建"。

## db / sql

### E-020 删用户前先按外键顺序清表

- 场景：清理测试数据 `delete from users where email like 'smoke+%'`。
- 现象：`violates foreign key constraint "payments_order_id_fkey"`，一条条试很费时间。
- 根因：订单/支付/凭证/权益/通知等表都挂着外键，删除有严格顺序。
- 修法：按依赖从叶子往根删（可放进一个事务，失败自动回滚）：
  `entitlement_logs → entitlements → payment_claims → payment_amount_reservations → payments → outbox_events → orders → notifications → users`。
  先查哪些表带 `user_id`：`select table_name from information_schema.columns where column_name='user_id' and table_schema='public';`
- 教训：清理脚本要先跑一次"最小复现"，并把顺序写进文档；生产库执行前必须备份。

### E-021 迁移脚本/清理脚本要用事务包起来

- 场景：一次 `-c` 里塞了 8 条 delete，中途一条失败。
- 现象：前面几条已生效、后面没执行，数据处于半清理状态，再跑报"找不到行"。
- 根因：psql 默认 autocommit，每条语句独立提交。
- 修法：`begin; ... commit;`（或 `psql -1`），失败即整段回滚，可安全重试。
- 教训：任何"多条语句构成一个意图"的操作都要事务；重试安全比一次成功更重要。

## docker / infra

### E-030 沙箱里 `docker ps` 报 socket permission denied

- 场景：在受限沙箱中执行 `docker ps`。
- 现象：`permission denied while trying to connect to the Docker daemon socket`。
- 根因：沙箱不放行 unix socket，跟 Docker 本身无关。
- 修法：这类命令按"需要更高权限"处理，单独申请执行；不要误判为 Docker 服务没启动。
- 教训：先分辨"环境限制"与"真实故障"，再动手修。

### E-031 绑定 `localhost` 的容器端口在宿主访问不到

- 场景：容器内服务监听 `127.0.0.1`，宿主 `curl localhost:<port>` 不通。
- 现象：连接被拒，容器日志显示已就绪。
- 根因：容器内的 `127.0.0.1` 是容器自己的回环，与宿主不是同一个网络命名空间。
- 修法：容器内监听 `0.0.0.0`（Next standalone 用 `HOSTNAME=0.0.0.0`）。
- 教训：容器里"能启动"不等于"能被访问"，先看监听地址再看端口映射。

### E-086 Docker 构建缓存会无限膨胀，最后撑爆磁盘

- 场景：反复 `docker compose build` 部署（每次本地部署/CI 都重建镜像）。
- 现象：某天磁盘 100% 满，`docker system df` **卡住不返回**，`docker ps -a` 显示**所有容器 Exited**，
  站点整体打不开。表面症状像"容器莫名集体退出"，跟磁盘看不出关系。
- 根因：Build Cache 只增不减——一台 40G 的机器上实测涨到 **15.01GB**（`docker system df` 的
  `Build Cache` 那一行）。加上悬空镜像 2.5GB、journald 日志 3.8GB，直接把盘写满。磁盘满之后
  dockerd 无法落盘、异常重启，容器随之全部停止。
- 修法：
  ```bash
  df -h /                        # 服务群集体挂掉，先看这个
  docker system df               # 再看 Build Cache / Images 两行
  journalctl --vacuum-size=200M  # 日志：立竿见影，常能回收几个 G
  docker builder prune -f        # 构建缓存：本次回收 15G，磁盘 90% → 50%
  ```
  持久做法三条：① 部署脚本每次成功后 `docker builder prune -f --keep-storage 2GB`
  （保留最近几层，下次构建仍有加速，又给增长设了上限）；② `/etc/systemd/journald.conf` 设
  `SystemMaxUse=200M`；③ `daemon.json` 加 `log-opts: {max-size: 10m, max-file: 3}`。
- 教训：**服务群集体挂掉，第一件事是 `df -h`，不是翻应用日志**。构建缓存是隐形的，
  没有任何东西会提醒你它在长。

### E-087 `restart: unless-stopped` 挡不住"被手动停止"

- 场景：容器配了 `restart: unless-stopped`，指望 Docker 守护进程重启后服务自动回来。
- 现象：dockerd 重启后容器**没有**起来，日志只有一句
  `ShouldRestart failed, container will not be restarted ... hasBeenManuallyStopped=true`。
- 根因：`unless-stopped` 的语义是"**除非它被显式停过**就不重启"。容器一旦被标记为手动停止
  （`docker stop`、`docker compose down`，或守护进程异常时的记录），重启守护进程也不会拉起它。
- 修法：要"一定自愈"就用 `restart: always`；改完**同时热应用**，免得为了改策略去重建容器：
  ```bash
  docker update --restart=always $(docker ps -q)
  ```
- 教训：两种策略平时看不出差别，只在**守护进程重启**那一刻才显形——那时你才发现它没起来。

## toolchain / network

### E-064 日志的定位字段要"从调用点推导"，不要让业务代码手写

- 场景：想让每条日志都能看出"哪个模块、哪个函数、哪一行"。
- 坑：靠人工传 `module="payment"` / 手写函数名，必然漏、必然过期（重构后没人改），最后变成假信息。
- 修法：做一个包住 slog handler 的薄封装，在 `Handle` 里用 `record.PC` + `runtime.CallersFrames` 推导：
  `src_module`（从文件路径取模块名）、`func`（去掉仓库前缀）、`caller`（`文件:行号`）——业务代码一行都不用改。
  注意别直接用 slog 的 `AddSource`：它只给 file:line，**函数名不会打印出来**。
- 教训：**能被机器推导的元数据，永不让人类手写**。这条同样适用于请求 ID、用户 ID、耗时。

### E-065 上下文 logger 必须有 fallback 链，否则后台任务会掉进默认 logger

- 场景：请求中间件把带 `trace_id` 的 logger 放进 context，业务代码统一 `FromContext(ctx)` 取。
- 现象：跑单测/定时任务时日志莫名打到 stderr（默认 logger），还带不出任何上下文；测试断言也抓不到。
- 根因：`FromContext` 在"没有请求上下文"时直接回退 `slog.Default()`；而后台任务/测试根本没有请求级 logger。
- 修法：三档 fallback —— 请求级 logger → 服务自己的 logger（构造函数注入，`FromContextOr(ctx, s.log)`）→ `slog.Default()`。
  测试里用 `NewWithWriter(env, level, buf)` 之类可注入 writer 的构造器，断言才抓得住输出。
- 教训：**"取不到就用默认"是个隐形陷阱**——默认值往往是全局单例，会绕过你的所有上下文与测试边界。

### E-066 日志回流要有三道保护，否则"日志故障"会变成"业务故障"

- 场景：前端把 warn/error 上报到后端，写进同一条日志流（这样 trace_id 能串起来）。
- 风险：前端死循环报错 → 每秒几千条上报 → 打满带宽/磁盘/CPU；后端日志接口本身报错 → 递归上报 → 雪崩。
- 修法：
  1. **只回流高价值级别**（warn/error），debug/info 留在浏览器控制台；
  2. **两端限流**：前端批量（攒 10 条或 3 秒）、`keepalive` 补发；服务端限制单批条数、请求体大小、每 IP 每分钟次数，超限 429；
  3. **失败即丢、绝不重试、绝不递归**（上报请求本身不走统一请求封装，也就不会触发上报）。
- 教训：任何"旁路系统"（日志、监控、埋点）都必须假设自己会失败，并且**失败时不能影响主链路**。

### E-061 自己写 Reader 时，`(0, nil)` 必须当成异常处理

- 场景：实现 `io.Reader`（HTTP 流、对象存储分块读、解密流等），内部按需重新拉取数据。
- 现象：进程 100% CPU 卡死，`io.ReadAll` 永不返回；日志里没有报错。
- 根因：`Read` 返回 `(0, nil)` 时调用方会**继续循环**。常见触发点有两种：
  1. 服务端/代理提前结束响应（比如声明的 `Content-Length` 与实际写入不一致），读端拿到 `EOF` 但自己的"区间结束位置"还停留在文件末尾，于是既不报错也不前进；
  2. 底层流返回 `(0, nil)`（合法但不表示结束）。
- 修法：
  - 拿到 `EOF` 而总进度还没到末尾 → **把当前流的覆盖区间收敛到实际进度**，释放连接，下一次 `Read` 重新发起 Range 请求续传；
  - 加"连续空读"计数（3 次就返回错误），保证最坏情况也能失败退出，而不是死循环；
  - 单测里专门造一个"响应体比声明短"的假服务端，把这条路径钉住。
- 教训：**任何可能返回"零进展"的循环都要有兜底条件**；"不会出错"的分支最容易写成死循环。

### E-062 自己实现标准协议（签名/编码）要用"官方向量 + 真实服务"双重验证

- 场景：不引 SDK，手写 AWS SigV4 这类有规范但有细节坑的协议（规范化 URI、header 排序、时间格式、派生密钥链）。
- 坑：只跑自己的实现，签名看起来"能生成"，但对端一律 403，且无法判断错在哪一步。
- 修法：
  1. **官方向量**：把规范文档里带固定时间/固定密钥/已知签名值的例子固化成单测（纯函数输入输出，秒级反馈）；
  2. **真实服务**：用 `httptest` 造假对端验证请求形状（header/路径/Range），再拉一个真实服务（如 MinIO 容器）跑一次上传+下载，确认互操作；
  3. 真实服务那一步写成**环境变量开关的集成测试**（没设变量就 skip），CI 保持快，本地可跑真。
- 教训：自实现协议的风险不在"写不出来"，而在"错了不知道"；两道验证的性价比远高于引依赖。

### E-060 拆大文件时，用"构建错误驱动"清 import + "代码行集合比对"证明零丢失

- 场景：把一个 690 行的组件文件按职责拆成 3~5 个文件（同包内拆，不改结构）。
- 坑一：每个新文件都要自己的 import 块，手写必然出错（少写 → 编译失败；多写 → `imported and not used`）。
- 坑二：拆完怎么证明"没漏抄一段代码"？靠肉眼 review 不可靠。
- 修法：
  1. **先用工具的报错生成答案**：新文件先带上完整 import 块，然后反复跑构建，按报错删除未使用的 import，直到构建通过（错误里两种格式都要匹配：`"x" imported and not used` 与 `"x" imported as alias and not used`）。删除时按**引号内的路径**精确比较，否则会误删路径互为前缀的导入（如 `a/domain` 与 `a/domain/sub`）。
  2. **零丢失校验**：把拆分前文件的"非空非注释行"做 `Counter`，与拆分后所有新文件的同集合比较；`旧 - 新` 必须为空，`新 - 旧` 只应包含 `package` / `import` / 文件头注释行。一行都不能凭空消失。
  3. 最后 `gofmt -w` + `go vet` + 跑一次真实业务链路（本项目是 `scripts/smoke.sh --full`）。
- 教训：**重构的验收靠机器，不靠眼睛**。两个可复制的机械校验（导入清理、行集合比对）比读十分钟 diff 更可靠。

### E-040 沙箱内网络访问失败要换权限重试，而不是换方案

- 场景：`git push` / `npx` / `ssh` 报 `Operation not permitted` 或连接超时。
- 现象：看起来像"对端挂了"或"DNS 坏了"。
- 根因：沙箱默认限制出网。
- 修法：同样的命令申请更高权限重跑；成功后再判断是否真有对端问题。
- 教训：报错先看**错误类型**（权限 vs 网络 vs 业务），别急着改技术方案。

### E-041 `npx --yes <pkg>` 是验证工具链的最快方式

- 场景：临时需要代码生成器/校验器（openapi-typescript、redocly 等）。
- 修法：`npx --yes <pkg>@<major>` 直接跑；确定要长期用再加进 `devDependencies` 并提交 lock 文件。
- 教训：先用一次性执行验证价值，再固化成项目依赖，避免 package.json 里堆一堆只用过一次的工具。

### E-088 Tailscale 会掐掉阿里云的内部 DNS 与元数据服务

- 场景：在阿里云 ECS / 轻量服务器上装 Tailscale 并 `tailscale up`。
- 现象：**装完 VPN 后服务器上所有域名都解析不了**（连 `google.com` 都不行）。`dnf install` 装不了包、
  ACME 签不了证书、Caddy 的续期迟早也会失败。但看起来"网络是好的"——`ping 8.8.8.8` 通、服务本身没挂。
- 根因：Tailscale 会装一条 iptables 规则 `DROP all -- 100.64.0.0/10`（防源地址伪造）。
  而**阿里云的内部 DNS 是 `100.100.2.136` / `100.100.2.138`、元数据服务是 `100.100.100.200`，
  全都落在 `100.64.0.0/10` 里**。DNS 应答的源地址是 `100.100.2.136` → 被当成伪造包丢弃。
  查询发得出去、应答进不来，所以症状是"超时"而不是"拒绝"。
  两个把人带偏的假线索：① `ip route get 100.100.2.136` 显示走 eth0，**路由完全正确**；
  ② `ping 100.100.2.136` 不通——但 DNS 服务器本来就不回 ICMP，不能作为判据。
  确认方法：直接用 UDP 打 DNS，绕过系统解析器，再拿 `8.8.8.8` 做对照（一个通一个不通，
  就说明是"特定来源被丢"而不是"DNS 全挂"）：
  ```bash
  python3 - <<'PY'
  import socket, struct, random
  def q(srv, name='google.com'):
      pkt = struct.pack('>HHHHHH', random.randint(0,65535), 0x0100, 1, 0, 0, 0)
      pkt += b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\x00'
      pkt += struct.pack('>HH', 1, 1)
      s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(4)
      try:
          s.sendto(pkt, (srv, 53)); s.recvfrom(512); return '通'
      except Exception as e: return f'不通({type(e).__name__})'
      finally: s.close()
  for ip in ('100.100.2.136', '100.100.2.138', '8.8.8.8'):
      print(f'  {ip:16} -> {q(ip)}')
  PY
  # 再看规则本身：iptables -L ts-input -n | tail -3 → 会看到 DROP 100.64.0.0/10
  ```
- 修法：关掉 Tailscale 的 netfilter 管理，让它不要动 iptables：
  ```bash
  tailscale up --netfilter-mode=off --hostname=<名字> --accept-dns=false
  ```
  设置写进 prefs，重启 tailscaled 后保留。代价是少一层防源地址伪造的包级防护；
  tailnet 里只有自己设备的场景可以接受。
- 教训：**在云厂商主机上装叠加网络（Tailscale / ZeroTier / WireGuard 自建）后，
  第一件要验证的不是"VPN 能不能连"，而是"这台机器还能不能解析域名、能不能读实例元数据"**
  —— 云厂商的内部服务经常用 `100.x` / `169.254.x` 这类特殊网段，与叠加网络自己的网段天然冲突。

### E-089 Tailscale Serve 会被既有的 `0.0.0.0:443` 反代挤掉

- 场景：主机上已经有反向代理（Caddy / Nginx，尤其跑在 Docker 里映射 `0.0.0.0:443`），
  再启用 `tailscale serve`。
- 现象：`tailscale serve status` 显示配置正常、证书也签下来了（tailscaled 日志有 `got cert`），
  但浏览器访问 `https://<magicdns>/` 报 **`tlsv1 alert internal error`**（curl 报 `error:14094438`）。
  看起来像证书问题，其实是**连接被别的进程接走了**。
- 根因：Tailscale Serve 固定要占 443。当 `0.0.0.0:443` 已被 docker-proxy 占用时，
  `ss -tlnp | grep :443` 只会看到 docker-proxy，而 **Tailscale IP 上没有任何监听**
  （`ss -tlnp | grep <tailscale-ip>` 为空）。访问 Tailscale IP 的 443 命中 `0.0.0.0` 通配监听，
  落到那台反代上；反代不认识这个 SNI，回一个 TLS internal error。
- 修法：把 serve 换到别的端口，别动生产反代：
  ```bash
  tailscale serve reset
  tailscale serve --bg --https=8443 http://127.0.0.1:<目标端口>
  # 访问地址变成 https://<magicdns>:8443/
  ```
  如果这个 serve 是被某个程序托管的（例如 OpenClaw 的 `gateway.tailscale.mode: "serve"`），
  要先把托管关掉（改成 `off`），否则它重启时会把 443 的配置写回来，把手工配置顶掉。
- 教训：**"TLS internal error" 不等于证书有问题**。先问"这条连接到底落在谁身上"——
  `ss -tlnp | grep :443` 看是哪个进程，再看目标 IP 上有没有专用监听。
  通配绑定（`0.0.0.0`）会悄悄吃掉本该属于别人的流量。

## git

### E-063 有 `go.work` 的仓库，本地全绿 ≠ CI 全绿

- 场景：monorepo/多仓共用工作区（`go.work` 把多个模块串起来），其中一个模块新引入了第三方包。
- 现象：本地 `go vet ./...` / `go test ./...` 全过；推到 GitHub 后 CI 在 `go vet` 就失败：
  `missing go.sum entry for module providing package gopkg.in/yaml.v3; to add: go get -t ...`。
- 根因：**`go.work` 会合并所有工作区模块的依赖**，别的模块（或本地未发布的模块版本）顺手把包带进来了；
  CI 只 checkout 单个仓库，按它自己的 `go.mod`/`go.sum` 解析依赖 → 缺就直接失败。
- 修法：
  1. 补依赖到**出错模块自己的** `go.mod` + `go.sum`（测试文件 import 的包同样要声明，测试依赖也是依赖）；
     没网/审批不便时，可以从 `go.work.sum` 或同级模块的 `go.sum` 里取哈希手工补两行（`h1:` 与 `/go.mod h1:`）；
  2. 增加一条 **CI 等价命令**并写进 Makefile，提交前必跑：
     `cd apps/api && GOWORK=off go vet ./... && GOWORK=off go build ./... && GOWORK=off go test ./...`；
  3. 复现 CI 失败的最快方式就是给命令加 `GOWORK=off`——它能立刻暴露"只在工作区里成立"的依赖。
- 教训：**本地环境比 CI 宽松时，任何"本地绿"都不算证据**。为每个 CI job 准备一条本地等价命令，比事后读日志便宜得多。

### E-050 沙箱里 GitHub HTTPS 不稳定就用 SSH

- 场景：`git push` 报 `Empty reply from server` / HTTP2 framing 错误。
- 修法：改用 SSH remote；必须走 HTTPS 时加 `-c http.version=HTTP/1.1`。
- 教训：把"哪种通道能通"记在项目文档里，别每次重新排查。

### E-051 生成物要提交进仓库，但要加漂移门禁

- 场景：代码生成器（类型、schema、文档）的产物。
- 现象：不提交 → 同事本地类型滞后；提交 → 忘记重新生成就漂移。
- 修法：提交生成物 + CI 里"重新生成后 `git diff --exit-code`"。
- 教训：`git diff --exit-code` 只有**提交之后**才有意义（未提交时必然报差异），本地把它当提交前最后一跑。

## 第三方 SaaS 接入（Sentry 等）

### E-079 异步消费速率会被 tick 频率锁死（积压要 drain，参数要可配）

- 场景：事务性 outbox（钱到账 → 发权益）。消费者是"定时批量拉取"：批 20 条 / 每 3 秒。
- 现象：功能测试全绿、日常也无感；**压测 1000 单时暴露**——支付侧 1000 单全部成功，
  但只有 880 个用户拿到权益，120 条事件还在队列里（用户要等 2~3 分钟，高峰期持续积压）。
- 根因：消费能力 = 批大小 / 间隔 ≈ **6.7 条/秒**，被 tick 频率锁死；
  这个上限在低流量下永远看不见，只有突发流量才暴露。
- 修法（三件一起做）：
  1. **批大小与间隔做成配置**（本项目默认 100 条 / 1 秒 ≈ 100 条/秒）；
  2. **积压时连续消费（drain）**：只要上一轮把批次取满，就立刻再取一轮，不等下一个 tick；
  3. 每条处理都打日志（`outbox.processed`），积压时能从日志看出速率与堆积。
- 复测：1000 用户 / 100 并发 → 1000 单 paid、1000 权益、**积压 0**。
- 教训：**异步链路的消费速率必须和入口速率同量级**，否则"最终一致"会变成"最终很慢"；
  验收异步系统不能只看功能用例，必须**跑一次突发流量**。

### E-080 压测工具自己会骗人：先怀疑工具，再怀疑系统

- 场景：自研并发压测工具（模拟官方回调 + 统计结果）。
- 现象：DB 里 100 单全部 paid、100 份权益、outbox 清空，但工具报"100 个回调请求失败"。
- 根因（两个都是工具的问题）：
  1. 结果分类里用了**从未赋值**的 `httpCode` 字段 → 所有请求都落到失败分支；
  2. "金额不符"负例跑在**已支付**的订单上——支付单已是 succeeded，按状态查询根本取不到，
     于是它只落到 `unmatched`，永远测不到"金额校验 → rejected"这条分支。
- 修法：按真实错误（`err != nil`）分类；负例必须用**符合前置条件的样本**（新建一张未支付订单）。
- 教训：**压测工具的红/绿都可能是假的**——出现"工具说失败、数据库说正常"时，
  先核对指标口径与样本前提，再动手改系统；否则会照着假信号去修不存在的问题。

### E-077 幂等键要绑"业务事实"，不是绑"代码路径"

- 场景：订阅权益的发放逻辑是"重复购买则在原到期时间上顺延一个月"（正确的续期语义）。
  outbox 消费者重试同一条 `order.paid` 事件时，会再调一次发放 → **又顺延一个月 = 免费续期**。
- 现象：功能测试全绿（单次发放正确），只有"重放同一条事件"的测试才会暴露；
  这种 bug 在钱上是静默的（用户白拿一个月，没人报错）。
- 根因：把"续期"绑在了**动作**（调用发放）上，而不是绑在**事实**（哪一笔付款）上。
  upsert 的"冲突即顺延"语义本身没错，错在它被事件重放触发了。
- 修法：加一张**发放事实表**（如 `entitlement_grants`，`UNIQUE (source_type, source_id, product_id)`），
  在同一事务里先登记事实：冲突 → 直接返回既有结果、**不产生任何副作用**（不写审计、不改有效期、不打发放日志）；
  插入成功 → 才执行真正的发放。并且写一条**对照实验测试**（直接调 upsert 会顺延）把 bug 变成可复现事实。
- 教训：判断幂等是否做对，问一句"**重放同一条业务事件会发生什么**"——答案必须是"什么都不会发生"。

### E-078 共享测试库要显式串行化，且清库不能碰迁移账本

- 场景：给项目加真 Postgres 集成测试，用 `TEST_DATABASE_URL` 开关（未设置就跳过）。
- 现象一：`go test ./...` 时多个包的测试**并行**跑同一个库，迁移互相打架：
  `duplicate key ... pg_type_typname_nsp_index`、`relation "users" already exists`。
- 现象二：清库助手把 `schema_migrations` 一起 truncate 了 → 迁移账本丢失但表还在，
  下次迁移重放 0001 直接报"表已存在"，越修越乱。
- 修法：
  1. 用 Postgres **会话级 advisory lock**（`pg_advisory_lock(常量)`）把"迁移 + 清表 + 测试"整段串行化，
     测试结束释放；跨进程也有效，所以多个测试包/多个 CI job 共享一个库也安全；
  2. 清表脚本**显式排除 `schema_migrations`**（迁移账本是基础设施，不是业务数据）；
  3. 迁移本身保证幂等（记账 + 每步事务），失败整体回滚。
- 教训：**"共享资源 + 并行执行"永远需要一把锁**；测试基建里最容易忘的就是"迁移账本也是数据"。

### E-076 读"包外文件"的测试会被 go test 缓存假绿

- 场景：写一个门禁测试，校验 `docs/module-contracts.md`（协议索引）与代码/测试文件是否一致。
- 现象：故意删掉索引里的一行，`go test` 依然 `ok ... (cached)`——门禁看起来永远通过。
- 根因：`go test` 的缓存键只包含**包内**输入（源码、依赖、环境变量与少数参数），
  `os.ReadFile("../../docs/x.md")` 读的文件不在键里；文件变了缓存也不会失效。
- 修法：所有"读包外文件"的测试统一用 `-count=1` 运行（Makefile 目标、CI 步骤都带上），
  并在测试注释里写明原因；验证方式就是——**故意破坏一次，确认它真的会红**。
- 教训：**门禁要验收"它会红"**，否则等于没有门禁；同时记住任何"读外部状态的测试"都绕过了缓存假设。

### E-067 分清第三方 SDK 的凭据类型：Client Secret 不是 Auth Token

- 场景：在 Sentry 里建了 Internal Integration，拿到一串 64 位 hex，直接当 `SENTRY_AUTH_TOKEN` 用。
- 现象：`GET /api/0/projects/` 返回 `401 {"detail": "Invalid token"}`；换成另一个 64 位 hex 却是 `403`（已认证、权限不足）。
- 根因：Sentry 有两套凭据——**Client Secret**（OAuth 流程用）与 **Auth Token / Integration Token**（API 与 sentry-cli 用）。外形相似，用途完全不同；`401` 与 `403` 的差别就是"不是这个凭据" vs "是这个凭据但权限不够"。
- 修法：要上传 source map / 调 API，用带 `project:releases`（+ `org:read`、`event:read`）的 **Auth Token**。用 `401/403` 快速自检：401 换凭据，403 加权限。
- 教训：**401 = 凭据不对，403 = 权限不够**——先把这两种失败分开，再去翻文档，能省掉一轮瞎试。

### E-068 构建插件的 `silent: true` 会把诊断信息一起吞掉

- 场景：`withSentryConfig({ silent: true })`（为了让 CI 日志干净）。
- 现象：source map 上传"看起来没问题"，实际 artifacts 是 0；没有任何报错，因为插件把警告也静默了。
- 根因：`silent` 是全局静默，既关掉正常输出也关掉失败提示。
- 修法：把静默做成**环境变量开关**（如 `SENTRY_VERBOSE=1` 时 `silent: false`），平时干净、排查时打开；排查完就能看到 `Successfully uploaded source maps` 或具体错误。
- 教训：任何"静默模式"都要留一个一键打开的后门，否则故障时你连它失败过都不知道。

### E-069 前端构建期变量必须走 build args，改完要重建镜像

- 场景：`NEXT_PUBLIC_SENTRY_DSN` / `NEXT_PUBLIC_APP_RELEASE` 只写进容器的运行时 `environment`。
- 现象：浏览器端 SDK 永远不生效（或 release 显示 unknown），服务端却正常。
- 根因：`NEXT_PUBLIC_*` 是**构建期内联**进 JS bundle 的，运行时注入对已构建的产物无效。
- 修法：Dockerfile 声明 `ARG`+`ENV`，compose 从环境/`.env` 传 `build.args`；**改完必须重建镜像**（`up -d --build`），只重启容器没用。
- 教训：分清楚"构建期"与"运行期"变量；同理，上传 source map 的 release 名也要在 build 阶段注入，否则会出现"map 归一个 release、事件归另一个"。

### E-070 新版 Sentry 的 source map 走 debug ID，别用 release files 数量判断成败

- 场景：想验证 source map 是否上传成功，去查 `releases/{version}/files/`。
- 现象：返回 0 个 artifact，看起来上传失败；但构建日志明明写着成功。
- 根因：现代 SDK 用 **debug ID + artifact bundle** 关联，不再往 release 挂文件；`release files` 只对旧流程有意义。
- 修法：验证看两处——① 构建日志里的 `Successfully uploaded source maps`（三端各一条）；② **触发一条新错误**，看栈帧是否变成源码文件+行号（旧事件不会追溯符号化，要新事件）。
- 教训：验证要用**对端能证明的信号**（栈可读），而不是自己这边的中间指标（文件数）。

### E-074 验证第三方接入要查"对端真相"，注意 API 端点与 scope 的坑

- 场景：接完 Sentry 想确认事件真的到了。
- 现象：`/api/0/projects/{org}/{project}/events/{id}/` 403；换了路径 `/api/0/issues/{issue_id}/events/latest/` 却 200 并拿到完整栈帧。
- 根因：同一个资源可能有多个端点，权限要求与可见性不同；token 缺 `event:read`/`org:read` 时多数端点 403，容易被误判为"事件没到"。
- 修法：① 先 `GET /api/0/auth/` 或在 UI 里确认 token 的 scopes；② 用 `/api/0/projects/{org}/{project}/issues/?sort=date` 列 issue；③ 用 `/api/0/issues/{id}/events/latest/` 读事件与栈帧；④ org slug 可以从 issue 直链（`https://<org-slug>.sentry.io/issues/<id>/`）反查。
- 教训：**"查不到"和"没成功"是两件事**；在判定失败前，先确认自己的查询方式有权限。

## 部署与告警噪音

### E-075 CLI 的参数形态会变：报错先看 `--help`，别照抄旧文档

- 场景：照着文档执行部署标记：`sentry-cli releases deploys new <version> -e production`。
- 现象：`error: unexpected argument '<version>' found` + `Usage: ... --env <ENV>`。
- 根因：新版 CLI 把版本号从**位置参数**改成了 `--release <VERSION>`；文档与旧脚本没跟上。
- 修法：`<subcommand> --help` 永远以本地安装的版本为准；把正确形态写回脚本与文档（本项目 `deploy.sh` 第 7 步）。
- 顺带一条同源经验：同一份数据的查询端点也可能换家——Sentry 的 deploys 在 **org 级**路径能查
  （`/api/0/organizations/<org>/releases/<v>/deploys/`），project 级会 404。
- 教训：**报错信息里已经写了正确用法**（`Usage:` 一行），先读它，比翻文档快得多。

### E-072 Postgres 22P02 是客户端输入问题，不该变成 500

- 场景：业务主键是 `uuid`，接口直接把路径/body 里的字符串透传到 `$1::uuid`。
- 现象：请求 `/payments/not-a-uuid` → Postgres 报 `22P02 invalid input syntax for type uuid` → 被当成服务端异常，返回 500 并触发告警。
- 根因：DB 的类型错误被错误地归类成"服务端故障"；实际上它是**客户端给了非法字面量**。
- 修法：① 统一兜底——识别 `22P02`（`errors.As` 到 `*pgconn.PgError`），在各模块的错误映射里转成 **400**；② 边界校验——body 里的 UUID 字段（`offer_id`/`product_id` 等）在 handler 里先 `IsUUID` 拦掉。
- 教训：**输入错误不该走 500 通道**——既误导用户（"服务异常"），又污染告警配额；告警一旦被假阳性占满，真故障就没人看了。

### E-073 部署窗口的瞬时错误会造成假告警

- 场景：滚动重建容器（`up -d --build`）时，前端 SSR 正在请求后端，后端容器短暂不可用。
- 现象：Sentry 出现"请求失败（网络层）"的真实用户事件，时间点与 deploy 完全吻合。
- 根因：部署本身会产生秒级连接失败；把它当 error 上报，等于**每次部署都自动生成一条告警**。
- 修法：① 网络层失败（连不上/DNS/中断）降级为 **warn** 并打 `ssr` 标记，5xx 与业务错误仍为 error；② 有条件的话给每次部署打 **deploy 标记**（`sentry-cli releases deploys new`），Sentry 里能看出"这条错误紧跟某次部署"；③ "服务真的挂了"交给 `/readyz` 探针 + uptime 监控判断。
- 教训：**告警要按"是否需要人立刻动手"分级**；把可预期的运维抖动也告警，最后的结果是没人看告警。

## 框架与库的行为差异

### E-071 chi 的 `router.Use` 在路由匹配之前执行，拿不到 URL 参数

- 场景：想写一个全局中间件，校验所有 `/payments/{paymentID}` 这类路径参数是不是合法 UUID。
- 现象：中间件里 `chi.RouteContext(ctx).URLParams` 是空的，校验永远不生效（测试里表现为"非法参数返回 200"）。
- 根因：chi 的 router 级中间件包裹的是"路由分发"本身，**在匹配发生之前**执行；URL 参数是匹配的产物。
- 修法：三条路——① 用 `r.With(mw).Get(...)` 逐路由挂（匹配后执行，能拿到参数）；② 在 handler 里校验；③ 在 DB 错误层统一兜底（本项目选它 + body 字段显式校验）。
- 教训：**中间件的执行时机决定它能看见什么**；写完一定要用测试证明"它真的拦住了"，否则会留下"看着有防护其实没有"的假象。

## 压测与验证（工具本身也会骗人）

### E-081 断言口径必须按"本轮数据"切分，否则共享库上的结论随历史漂移

- 场景：压测/验收脚本在共享开发库或测试库上查 `count(*)` 做断言（如"生效权益数 = 已支付订单数"）。
- 现象：报「生效权益=2420 与已支付订单=20 不一致」，看起来像严重超发；实际是几天来所有历史压测用户被算了进来。
- 根因：筛选用的是**类别条件**（`email like 'payload-%'`），而库里同时存在多轮运行的数据。
- 修法：本轮数据一律用**运行开始时间戳**切分（`created_at >= to_timestamp($RUN_START)`），
  并让压测数据带统一标记（`source like 'payload%'`），清理 SQL 也按同一口径写。
- 教训：**测试断言的"数据范围"必须显式**。凡是"全局 count"的断言，在共享环境里迟早会漂。

### E-082 最终一致的链路，验证必须自带"等到稳定"语义

- 场景：压测工具返回后立刻查库校验异步链路（outbox 消费、事件驱动的权益发放/冲销）。
- 现象：第一阶段全绿，第二阶段立刻报「outbox 未完成=5」；手工再查一次，5 条已 `done`。
- 根因：异步消费者有 tick/批量延迟；而"等待条件"如果依赖了本次恰好已经满足的指标（乱序样本本来就没有权益可冲销），
  等待会瞬间通过，起不到"等收敛"的作用。
- 修法：断言前**轮询到稳定**（最多 N 轮 × 固定间隔），条件是"所有异步指标同时达标"（outbox 排空 **且** 业务计数一致）；
  超时后再判定失败。
- 教训：**red/green 不能取决于手速**。异步链路的验收要有明确的收敛判据与超时。

### E-083 压测工具只在失败时走的那几行，恰恰最没被测过

- 场景：压测工具用 `atomic.Value` 记录"第一个错误"：`firstErr.CompareAndSwap(nil, err)`。
- 现象：并发压测中工具自己 `panic: sync/atomic: compare and swap of inconsistently typed value into Value`，
  外层只看到 `exit status 2`，把真正的业务错误（503 金额池耗尽）完全盖住。
- 根因：`atomic.Value` 要求前后类型一致；先存过 `error` 接口之后再用 `nil` 比较会 panic——
  而这段代码只在"真的出现错误"时执行，平时永远是绿的。
- 修法：用 `sync.Mutex` + 普通变量记第一个错误（或 `atomic.Pointer[T]` 且类型固定）；
  并且给已知业务错误加人话提示（把根因写进错误消息）。
- 教训：**工具的失败路径也要压一次**（人为制造一个失败，看报错是否可读）。错误上报代码不跑通等于没有。

### E-084 容量上限要压出来，不然大促当天才发现

- 场景：用"金额指纹"（实付金额带唯一分位）区分付款人的收款码支付，`PAYMENT_AMOUNT_SUFFIX_MAX=99`。
- 现象：40 路并发申请 80 个订单时，创建支付单返回 `503 amount_unavailable`「当前没有可用的支付金额」。
- 根因：**同一时刻未支付的订单数 = 分位池占用数**，池子只有 99 个取值（两位小数决定的硬上限）；
  服务端生成金额的重试上限 20 次，高并发下全撞很正常。
- 修法：把这当成**容量参数**而不是性能问题：① 压测脚本在样本数逼近上限时提前警告；
  ② 工具把该错误解释成"池子打满"；③ 写清三条出路（调大分位空间 / 按时间窗轮换收款码 / 换带订单号的官方渠道）。
- 教训：**"能用"≠"能撑多少"**。凡是靠"空间换区分度"的设计（分位、序号、单号池），
  都要在压测里量化出并发上限，并写进文档和脚本的护栏。

### E-085 长驻的 dev 进程跑的是旧代码

- 场景：本地 8080 上跑着几天前 `go run` 起的 dev API；期间代码给接口加了新字段。
- 现象：用同一套脚本压测，8080 报「响应里没有 out_trade_no」；换个端口起当前代码后一切正常。
- 根因：旧进程不会因为源码变化而重启，接口形态停留在启动那一刻。
- 修法：验证/压测类任务**自己起一个当前代码的实例**（换端口），并在报告里注明端口与启动时间；
  排查"我代码明明改了"时，先确认目标进程的启动时间（`ps -o lstart=` / 容器 `StartedAt`）。
- 教训：**长驻进程是"环境事实"，不是"代码事实"**；验收前先确认被测对象是当前代码。

### E-090 读取条件 ≠ 约束条件：重试循环会把"偶发不一致"放大成"稳定失败"

> 编号说明：本条原为 E-086，与同日先提交的 E-086（Docker 构建缓存撑爆磁盘）撞号，
> 作为后加入的一条顺延为 E-090。

- 场景：用"唯一索引 + 重试"实现资源分配（金额指纹、序号池、单号池、短链后缀……）。
  唯一索引是 `unique (key) where status = 'active'`，而分配前的查询是
  `where status = 'active' and expires_at > now()`（多了一层过期过滤）。
- 现象：偶发 `amount_unavailable`「没有可用资源」，但表里明明只有几条占用；
  单独重试一次却能成功，看起来像随机故障。
- 根因：**过期但还没被定时任务清扫**的行：对索引来说仍占着位，对查询来说已经"不算占用"。
  分配算法又是确定性的（取最小空位），于是每次算出的候选都是同一条"过期行" →
  插入必撞唯一索引 → 重试 N 次全撞同一个键 → 对外报"池子满"。
  只在"清扫任务没跑"或"过期与下次清扫之间"的窗口里出现（典型 ≤1 分钟），
  并且只影响"最小后缀"那一个值——所以极难复现、极难归因。
- 修法：让**读取口径与索引条件逐字一致**；过期/失效的行在**分配事务里就地回收**
  （`update ... set status='expired' where status='active' and expires_at <= now()`），
  不要依赖定时任务兜底；重试循环里如果失败的还是同一个候选值，就应该把"池子满"和"撞了同一把锁"区分成两种错误。
- 教训：**凡是用"约束 + 重试"做分配的地方，先写下不变量（哪两处的条件必须一致），再让测试守住它**。
  否则失败信息（"资源耗尽"）会把人指向完全错误的方向。
  这条的收益：真凶隐藏了整整一天，靠一条"过期占用不该阻塞分配"的集成测试才钉死。

### E-091 验收/压测工具的三条铁律（第一版连踩三次，全是工具自己的错）

> 编号说明：本条原为 E-087，与先提交的 E-087（`unless-stopped` 不复活）撞号，顺延为 E-091。

- 场景：新写一个端到端"用户旅程"工具（浏览 → 注册 → 购买 → 学习 → 退款），第一次真跑。
- 现象：连红三次，每次故障都**不在被测系统里**：
  1. **选数据不合适**：按"第一个有付费报价的商品"挑，挑到咨询类商品（没有课时）→ 报"没有试看课时"；
  2. **等错状态**：支付回调后订单先变 `paid`，权益是异步发的，工具在"paid 但还没发权益"的窗口断言 → 误报 0 份权益；
  3. **用错角色**：拿管理员 token 去查用户订单（`/orders/{id}` 校验归属）→ 403。
- 修法（三条铁律）：
  1. **选数据要挑"能跑通的最小事实"**：候选必须同时满足全部前置条件，并逐条记录淘汰原因，
     全不可用时把原因列表打出来（"找不到"是最没用的报错）；
  2. **断言要等终极事实**：直接等"权益出现"，中间状态（paid/pending）只当诊断信息，
     不要用它当收敛条件——异步系统里"中间态"永远会骗人；
  3. **每个角色只用它自己的权限**：用户 token 查自己的订单，管理员 token 只做管理动作；
     混用会把"权限设计正确"误报成"接口坏了"。
- 附带收益：第 2、3 条暴露的真问题会转化成产品改进——例如"课程能买但课时没绑视频（409）"
  促成了在大纲接口里暴露 `has_video`，前端也能据此显示"待上传"。
- 教训：**工具必须真跑一遍才算写完**。写工具时的自查（"应该能跑"）和真跑之间，
  差的正是上面那三条；而这三条也只有真跑才会暴露。

### E-092 本地全绿 ≠ 提交绿：跨文件重构漏 stage 会让 CI 直接编译不过

> 编号说明：本条原为 E-088，与先提交的 E-088（Tailscale 掐掉阿里云 DNS）撞号，顺延为 E-092。

- 场景：把共享类型从 A 包挪到 B 包（1 个新包 + 1 个定义方 + 9 个调用方），
  本地 `go vet ./...`、单测、集成测试、端到端旅程全绿，然后提交。
- 现象：推上去的提交**编译不过**——CI 看到的是"函数已删、调用点还在"。
- 根因：`git add` 只加了新包与定义方所在目录，**9 个调用方留在工作区**。
  关键点：**工作区会把没提交的部分"补全"**，所以本地所有检查都会绿——它们检查的是工作区，
  CI 检查的是提交内容。这类"改一半"在跨文件重构（尤其挪包/改调用点/改签名）时最常发生。
- 修法（任选，越靠前越省事）：
  1. stage 前先 `git status --short` 数一遍文件数：横跨 N 个文件的改动只 stage 了 1/3，最该警觉；
  2. 提交后跑**干净检出验证**：
     `git worktree add --detach /tmp/ci-check HEAD && (cd /tmp/ci-check/<module> && GOWORK=off go build ./...)`；
  3. 推送前跑一遍等价于 CI 的本地命令（本项目 `make ci-api`），但它同样只反映工作区——
     所以第 2 条才是真判据。
- 教训：**"本地绿"证明的是工作区，不是那次提交**。跨文件重构的最低成本保险是干净检出编译一次；
  已经推上去的话，补一个小 commit 说明原因即可（历史留痕比悄悄 amend 更有价值）。

### E-093 本地 `next build` 与 `next dev` 共用 `.next`：验证构建用隔离副本

> 编号说明：本条原为 E-089，与先提交的 E-089（Tailscale Serve 443 被占）撞号，顺延为 E-093。

- 场景：前端有 dev server 在 `:3000` 跑着（`next dev`），同时在同一个目录跑 `npm run build` 验证构建。
- 现象：build 十几分钟没有输出（`| tail` 会缓冲输出，看不到进度），看起来像卡死；`.next` 里已有部分产物，
  但与 dev server 共用同一目录，状态互相覆盖。
- 修法：把 app **rsync 到 /tmp**（排除 `node_modules`、`.next`），`ln -s` 复用主工作区的 `node_modules`，
  在隔离副本里 `npm run build`：5 分钟内正常产出 `BUILD_ID` 与路由表。CI 本来就是干净 checkout，不受影响。
- 教训：**dev 和 build 别共用产物目录**；本地要验"能不能构建"，优先用隔离副本或先停 dev。
  另外：`npm run build | tail` 会吞掉进度输出，怀疑卡住时先看 `.next/BUILD_ID` 是否已生成，再决定是否中断。

### E-094 在国内用 iPhone 接私有网络：先确认它占不占 VPN 槽、登录要不要翻墙

- 场景：想让 iPhone 加入 tailnet（或其他私有网络）去访问自建服务。
- 现象（三个连环坑）：
  1. **Tailscale 在中国区 App Store 没有上架**——Apple lookup 接口 `country=cn` 返回 0 个结果，必须换美区账号才能下载；
  2. 装好后一启用就**占掉 iOS 唯一的 VPN 配置槽**，原来的翻墙 VPN 被踢下线；
  3. Tailscale 登录走 Google OAuth，而谷歌在国内需要那个已被踢下线的翻墙 VPN → **登录死锁**：
     想登进去必须先有 VPN，但打开 Tailscale 就没 VPN。
- 根因：iOS 系统层面同时只允许一个 NetworkExtension VPN 处于 connected 状态。这是系统限制，不是 App 的 bug。
- 治标的绕法：设置里先**关掉** Tailscale 的 VPN 配置 → 打开翻墙 VPN → 回 Tailscale 点登录、完成 OAuth（此时它没占槽）→ 登录成功后再启用。
  但登进去之后控制面仍在境外，**日常连通性依旧不保证**。
- 治本的做法：**别让手机依赖 VPN 槽**——把服务暴露成公网 HTTPS（Basic Auth + 应用令牌），手机浏览器直连。
  国内访问自己的境外机器通常没问题，这条路不占 VPN、不要谷歌账号、不受翻墙软件影响。
- 查区域可用性别靠记忆，用 Apple 公开接口：
  ```bash
  curl -s "https://itunes.apple.com/lookup?bundleId=io.tailscale.ipn.ios&country=cn" | jq .resultCount  # 0 = 未上架
  curl -s "https://itunes.apple.com/search?term=Termius&country=cn&entity=software&limit=3"            # 找同区域替代品
  ```
- 教训：**"手机加入私有网络"不是一句需求，是一组约束**——App 区域可用性、VPN 槽独占、登录链路是否依赖被墙服务，
  这三条要在动手前一次问清，否则会得到"装了但登不进、登进了又连不上"的循环。

### E-095 容器里的反向代理够不到宿主机的 `127.0.0.1`

- 场景：Caddy / Nginx 跑在 Docker 里，要反代一个只监听宿主机回环的服务（例如 OpenClaw 网关 `127.0.0.1:12319`）。
- 现象：容器里 `wget http://127.0.0.1:12319` 失败；换成宿主机的内网 IP 也失败——因为那个服务只绑了回环。
- 根因：容器有自己的网络命名空间，容器里的 `127.0.0.1` 是**容器自己**；
  `host.docker.internal` 解析到的是网桥网关 IP，同样不是回环。
- 修法：在宿主机上开一个**只绑内网 IP** 的中转，用 systemd 托管（`dnf install -y socat`）：
  ```ini
  [Service]
  ExecStart=/usr/bin/socat TCP-LISTEN:12320,bind=<宿主机内网IP>,reuseaddr,fork TCP:127.0.0.1:12319
  Restart=always
  ```
  Caddy 侧改成 `reverse_proxy <宿主机内网IP>:12320`。
  验证：`docker exec <caddy容器> wget -qO- http://<宿主机内网IP>:12320/...` 能拿到内容。
  中转端口不在云防火墙的放行列表里，公网不可达（实测确认过）。
- 教训：**"容器里的 127.0.0.1" 永远不是宿主机**。要么把服务绑到网桥可达的地址，要么加中转，
  别指望 `host.docker.internal` 能穿透回环绑定。

### E-096 `Authorization` 头一次只能承载一种认证

- 场景：Caddy 站点加 `basic_auth` 保护，而站点后面是一个用 `Authorization: Bearer <token>` 鉴权的 API
  （例如 OpenAI 兼容接口）。
- 现象：带 `-u user:pass` 调 API 返回 401；带 Bearer 调又被 Basic Auth 拦下——"认证怎么都不对"。
- 根因：两种认证都占用同一个 `Authorization` 头，后写的覆盖先写的；
  Caddy 的 `basic_auth` 会在入口把 Bearer 当 Basic 解析并拒绝。
- 修法：**按路径分流**，让 API 路径跳过 Basic Auth：
  ```caddyfile
  @api path /v1/*
  handle @api {
      reverse_proxy <backend>
  }
  handle {
      basic_auth { user <bcrypt-hash> }
      reverse_proxy <backend>
  }
  ```
- 教训：加一层认证前先确认下一层用什么头——**冲突发生在传输通道上，不在逻辑上**。
  同一个请求里不可能同时带 Basic 和 Bearer；要么分层（不同路径），要么只留一层。

### E-097 OpenClaw Control UI 首次连接要服务器端批准配对

- 场景：浏览器首次打开 OpenClaw Control UI，令牌正确、Basic Auth 也通过。
- 现象：`disconnected (1008): pairing required`，页面停在连接中，没有对话入口。
- 根因：每个新设备/浏览器都要显式配对，防止令牌泄露后被直接接管。这是设计，不是故障。
- 修法：
  ```bash
  su - admin -c "openclaw devices list"                    # Pending 里有 request id
  su - admin -c "openclaw devices approve <request-id>"    # 批准
  # 撤销某个设备：openclaw devices revoke <device-id>
  ```
  批准后刷新页面即可。配对状态存在服务器上，清浏览器缓存不影响。
- 教训：看到 `pairing required` **不要重装、不要改配置**——请求已经在服务器队列里等着批准。
 同类但不同的报错是 `unauthorized: gateway token missing`（没填令牌）——两者要分开判断：
  **token missing = 凭证没送到；pairing required = 凭证对了但设备未授权**。

## 课程站/粉丝站批量回填（2026-10，来自 docs/bug-log.md 复盘）

### E-098 持续写入的文件（日志/缓存/DB）别放在前端监听目录
- 场景：Next dev 下把开发日志写进仓库目录
- 现象：改一行代码反复重编译，页面卡顿
- 根因：文件监听把日志写入当成源码变更，形成重编译循环
- 修法：日志放仓库外（如 `/tmp/<project>-dev/`）；验证用生产模式启动
- 教训：监听目录只放源码；持续写入的文件一律放外面
- 分层：build/deploy

### E-099 go.mod 升版本要同步 Dockerfile 基础镜像
- 场景：`go.mod` 升到 `go 1.26`，Dockerfile 基础镜像还是旧 golang
- 现象：`docker build` 报 go.mod 要求更高版本
- 根因：编译器版本有三处要一致：go.mod、Dockerfile 基础镜像、本地 SDK/CI
- 修法：升级后三处逐一核对；Dockerfile 用与 go.mod 相同的 `golang:x.y`
- 教训：go.mod 变更时，Dockerfile 是"第二处需要同步的地方"
- 分层：build/deploy

### E-100 macOS 打包会带入 `._*` 元数据文件
- 场景：macOS `tar` 打包传到 Linux，迁移器扫描 SQL 文件
- 现象：报"无法解析 SQL 文件"（`._xxx.up.sql`）
- 根因：AppleDouble 元数据被打进包里，被当成迁移脚本
- 修法：`COPYFILE_DISABLE=1` + `--exclude='._*'`；解析器跳过 `.`/`_` 开头文件
- 教训：跨平台打包必须显式排除元数据；本地能跑 ≠ 打包后能跑
- 分层：toolchain/network

### E-101 领域对象不要直接当 API 视图；公开/后台视图必须分开
- 场景：handler 直接返回 domain 结构体；公开与后台共用同一个 view
- 现象：PascalCase 字段前端取不到；后台缺字段；会议链接险些从公开接口泄露
- 根因：Go 字段无 json tag → 输出 PascalCase；视图没按受众分层
- 修法：每接口过一层 view（显式 snake_case）；`slotView`（公开）与 `adminSlotView`（后台）分开
- 教训：200 不等于能渲染；共用视图的默认结局是"前台缺字段或后台泄露"
- 分层：其他

### E-102 "创建"接口要返回调用方真正要的业务码
- 场景：创建企业授权码
- 现象：界面拿到 UUID，用户没法输入"授权码"
- 根因：返回了数据库主键，而不是业务上的 LicenseKey
- 修法：返回 `{ID, LicenseKey}` 这类完整业务码
- 教训：写创建接口先问一句"调用方需要哪个标识"
- 分层：其他

### E-103 管道会吞退出码；部署验收要断言新版本特征
- 场景：`make deploy` 构建输出走 `| tail`；验收只查首页 200
- 现象：报错仍显示"部署完成"，线上还是老代码
- 根因：tail/tee 吞掉前序命令退出码，`set -e` 拦不住
- 修法：输出先落文件再 tail，显式 `exit $status`；验收检查"新接口/新页面"
- 教训：命令没报错 ≠ 动作发生了；首页 200 是旧版本也满足的条件
- 分层：build/deploy

### E-104 `git add -A` 前看 diff；CI 必须跑真 build
- 场景：编辑器保存到一半就 `git add -A`
- 现象：被截断的 layout.tsx 提交进仓库，干净克隆 `next build` 失败
- 根因：没看 `git status`/`diff --stat`；CI 只跑 typecheck 拦不住 JSX 结构错误
- 修法：提交前扫一眼变更清单；CI 跑真实 `build`
- 教训：typecheck ≠ build
- 分层：git

### E-105 兜底/演示数据必须显式标记，否则掩盖真实故障
- 场景：接口不可用回退演示数据；无报价渲染占位按钮
- 现象：真实数据在库里，页面显示内置演示课程；点"立即购买"无反应
- 根因：兜底逻辑静默顶替真实数据；占位控件没接逻辑
- 修法：兜底要有日志/标记；无数据显示明确提示而不是死按钮
- 教训：验收要能区分"真实数据"与"兜底数据"
- 分层：其他

### E-106 Next standalone 产物三件套：public / .next/static / 运行期变量
- 场景：`output:"standalone"` 的 Dockerfile 只拷 standalone + static
- 现象：线上收款码 404
- 根因：standalone 产物**不含** `public/`
- 修法：运行阶段 `COPY --from=build /app/public ./public`
- 教训：本地 `next start` 正常 ≠ 镜像正常
- 分层：build/deploy

### E-107 构建期变量 ≠ 运行期变量（SSR 需要运行时注入）
- 场景：`INTERNAL_API_URL` 只写进 compose 的 `build.args`
- 现象：SSR 拿不到数据，全站退回演示数据
- 根因：build args 只在构建期；服务端渲染发生在运行期，容器里没有这个变量
- 修法：compose 补 `environment.INTERNAL_API_URL`（运行期再注入一次）
- 教训：Node 侧 fetch 的 base 必须运行时可配；改完部署配置要验证"真实数据"而不是兜底
- 分层：build/deploy

### E-108 `gh auth status` 报 token invalid，先怀疑 keychain/沙箱
- 场景：沙箱内跑 gh 命令
- 现象：token invalid
- 根因：gh 凭证放 macOS keychain，沙箱读不到；沙箱外执行正常
- 修法：沙箱外执行，或改走 SSH
- 教训：看到 invalid 先怀疑环境，再怀疑令牌
- 分层：toolchain/network

### E-109 workflow 触发分支要覆盖实际开发分支
- 场景：工作流只配 `main`，实际开发在 `dev`
- 现象：push dev 不触发 CI
- 根因：`on.push.branches` 没含 dev
- 修法：branches 加 dev，或按 PR 触发
- 教训：CI 配置要与团队实际分支约定对齐
- 分层：git

### E-110 公网 443 打不开，先查云厂商防火墙
- 场景：服务器本机 ufw/iptables 全放行、docker 正常监听
- 现象：外网 https 打不开
- 根因：云控制台安全组/防火墙没放行 443
- 修法：云控制台放行 80/443；本机 `ss -lntp` 分清楚谁在监听
- 教训：链路排查从外到内逐层，别只查本机
- 分层：toolchain/network

### E-111 域名不解析先查实名认证/NS 委派；免费域名要有备用路径
- 场景：新购域名解析迟迟不生效；dedyn 免费二级域名暂停注册；无效 TLD 建 zone
- 现象：dig 一直查不到；`.zz` 这种 TLD 建了 zone 也永远解析不了
- 根因：未实名 → 注册局不发 NS 委派；免费域名政策会变
- 修法：先过实名；无效 TLD 别用；免费方案留备用路径
- 教训：DNS 生效的前提是"委派真正发布"
- 分层：toolchain/network

### E-112 幂等键别"先查再插"：唯一索引才是裁判，Redis 只做前置过滤
- 场景：实现"同键只执行一次"时先 `SELECT` 判存在，再 `INSERT`
- 现象：并发下两个请求都查到"不存在"，双双插入成功，重复订单/重复入账
- 根因：查询与插入之间存在竞态窗口；主从切换/Redis 丢写让外部缓存更不可靠
- 修法：`INSERT ... ON CONFLICT DO NOTHING`（或等价原子占位）抢执行权；插入成功=拿到执行权，
  冲突=别人在执行或已完成；Redis 只能做前置快速过滤，落库唯一索引才是最终裁决
- 教训：凡是"钱/权益/一次性动作"，防重的裁判必须落数据库唯一约束
- 分层：db/sql

### E-113 重试要复用同一键，且重复时返回首次结果而不是报错
- 场景：客户端双击/网络超时重发；每次重试都 `uuid.New()`；服务端重复时返回"已存在"
- 现象：幂等完全失效（每个请求都是"第一次"）；或客户端收到报错后无所适从——它还是不知道第一次到底成没成
- 根因：键必须在**意图产生时**生成一次并跟随整条重试链；"重复"的正确语义是"返回首次结果"
- 修法：客户端在进入下单页/发起点击时生成一次 `client_request_id`，重试复用；
  服务端存"键 → 处理结果"（processing/done/failed），done 时回放响应体；同键不同 payload 用 `request_hash` 拒绝
- 教训：键的作用域 = "你想让哪一类重复被视为同一件事"；换新键=防了个寂寞，报错=把不确定性还给客户端
- 分层：其他

### E-114 客户端幂等键用 sessionStorage，且"响应到达才换新"；localStorage 会过度幂等
- 场景：实现"下单防双击/防超时重发"的客户端 request_id
- 现象：用 localStorage 复用旧键 → 用户一周后下单，服务器命中旧幂等记录，把上周订单当本次结果返回
- 根因：键的生命周期绑"一次意图"（提交 → 收到确定性答复），不绑页面/会话；跨会话复用 = 过度幂等
- 修法：进入结算页 / 上次成功后生成新键写 `sessionStorage`；in-flight（含刷新）复用同一键；
  收到响应立即换新键；服务端 `UNIQUE(user_id, client_request_id)` + 返回首次结果 + 保留 24~72h
- 教训：刷新不该产生新意图；跨标签页/跨设备/长时间跨度由"业务相似单检测"兜底，不是幂等键的活
- 分层：其他

### E-115 VS Code Remote 的 server 断开后不会退出，会一直占磁盘和内存

- 场景：用 VS Code Remote-SSH 连服务器改代码，改完关窗口、断开 SSH。
- 现象：几小时后 `ps` 里仍有 6 个 `vscode-server` 进程（最大的 82MB RSS），但 `who` 没有任何登录用户、
  `ss -tnp | grep -E 'node|vscode'` 也没有 ESTAB 连接——进程却一直活着。
  同时 `~/.vscode-server` 占 **2.7GB 磁盘**。在一台 1.8G 内存的机器上，这批残留把可用内存压到 OOM 边缘，
  内核 24 小时内把 `openclaw-gateway` 杀了 6 次（systemd 反复拉起又被杀）。
- 根因：VS Code Remote **断开连接不杀 server**，为的是下次"秒连"复用已启动的 server 与扩展宿主。
  所以"关窗口 / 断 SSH / 合上笔记本"都不等于释放资源。
- 修法：
  - VS Code 命令面板 → **Remote: Kill VS Code Server on Host**（推荐，进程和目录一起清）
  - 或手动：`pkill -f vscode-server && rm -rf ~/.vscode-server`
  - 排查残留：`ps -eo rss,etime,cmd | grep vscode-server`、`du -sh ~/.vscode-server`
  - 判断是不是孤儿：`who` 为空 且 `ss -tnp | grep -E 'node|vscode'` 无 ESTAB
- 教训：
  - 在**小内存云主机**上，Remote-SSH 要当成"会常驻的服务"来管理，用完主动 kill，别指望断连接就释放。
  - **磁盘和内存是两个数**：2.7GB 是 `du -sh ~/.vscode-server` 的磁盘体积，进程 RSS 只有约 175MB；
    `ps` 的 VSZ（Node 常见 10GB+ total-vm）更不代表实际占用——看 RSS / `free -m` / `docker stats`。
  - 清理后立刻验证：`free -m` 看可用内存、`journalctl --since "5 min ago" | grep -c oom-kill` 应为 0。
- 分层：toolchain/network
