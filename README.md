# 个人学术主页与简历

一份数据，同时生成中英文网站和中英文简历。

```
data/profile.yaml        个人信息（公开）：教育、研究方向、简介、技能
data/publications.yaml   论文与著作（公开）：题目、状态、署名、概要、摘要
templates/               网页和简历模板
assets/                  样式表；照片也放这里
build.py                 构建脚本
docs/                    构建结果，网站就是这个文件夹（不要手改，每次构建会覆盖）
../cv_private/           私密信息和应聘版简历，不在本文件夹内，不会被推送
```

## 日常更新

1. 改数据：论文状态变了，只改 `data/publications.yaml` 里那一条的 `group` / `stage` / `venue`；个人信息改 `data/profile.yaml`；电话、出生年月、推荐人改 `../cv_private/private.yaml`。
2. 构建：

```bash
python3 build.py
```

3. 看结果：终端最后会列出所有还没填的 `[待填]` / `[待确认]`；网页和 PDF 里这些地方是黄色高亮。

生成的文件：

| 文件 | 用途 |
|---|---|
| `docs/index.html`、`docs/zh/index.html` | 英文、中文主页 |
| `docs/cv/Chao_Cheng_CV.pdf` | 英文简历（公开版，网站上可下载） |
| `docs/cv/Chao_Cheng_CV_zh.pdf` | 中文简历（公开版，不含电话、出生年月、推荐人） |
| `../cv_private/out/Chao_Cheng_CV_full.pdf` | 英文简历（含电话、推荐人），投递用 |
| `../cv_private/out/程超_简历_应聘版.pdf` | 中文简历（含基本信息、照片、推荐人），投递用 |

本地预览网站：

```bash
python3 -m http.server 8765 --directory docs
```

然后浏览器打开 http://localhost:8765 。

## 照片

照片是 `assets/photo.jpg`（480×600，由原图裁成 4:5 并压缩）。换照片时覆盖这个文件，重新构建即可。网站和中文应聘版简历都用它；英文简历按惯例不放照片。

## 上线（需要本人登录 GitHub）

上线前先确认终端里列出的待填项只出现在 `cv_private` 的应聘版里（公开文件里不能有）。

1. 第一次需要登录（会打开浏览器授权，只做一次）：

```bash
gh auth login --hostname github.com --git-protocol https --web
```

2. 在本文件夹里建仓库并推送（仓库名必须是 `charleschenggithub.github.io`）：

```bash
git init -b main && git add . && git commit -m "Initial site"
```

```bash
gh repo create charleschenggithub.github.io --public --source=. --push
```

3. 开启 GitHub Pages，指定从 `main` 分支的 `/docs` 文件夹发布：

```bash
gh api -X POST repos/CharlesChengGithub/charleschenggithub.github.io/pages -f "source[branch]=main" -f "source[path]=/docs"
```

几分钟后访问 https://charleschenggithub.github.io 。

以后每次更新：`python3 build.py`，然后 `git add . && git commit -m "Update" && git push`。

## 说明

- 网页只用系统字体，不加载任何境外资源（谷歌字体、CDN 脚本等），在国内打开不会卡在字体上。但 github.io 本身在国内偶尔访问不稳定，投递时以 PDF 简历为主，网址作为补充。
- 中文页面：中文稿显示中文题目和摘要；英文稿保留英文题目，没有对应中文摘要的显示英文摘要。
- 英文页面：中文稿显示英文译名并注明 "(in Chinese)"。
- `show: false` 的条目（目前是两个在研项目）不显示，改成 `true` 即可出现在网站和简历上。
