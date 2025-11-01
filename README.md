# 政府采购公告数据提取项目

基于 LangExtract + DeepSeek 的政府采购公告智能信息提取系统，能够自动从 HTML 格式的采购公告中提取结构化数据。

## 📋 项目简介

本项目使用大语言模型（DeepSeek）和 LangExtract 框架，从政府采购公告的 HTML 文件中自动提取关键信息，包括：

- 📅 公告时间
- 📝 项目名称
- 🏢 采购单位信息（名称、地址）
- 🏭 供应商信息（名称、地址）
- 💰 中标金额
- 📦 采购类别和标的

## 🚀 快速开始

### 环境要求

- Python 3.10+
- Conda（推荐用于环境管理）

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd data-extraction
```

2. **创建 Conda 虚拟环境**
```bash
conda create -n data-extraction python=3.10 -y
conda activate data-extraction
```

3. **安装依赖**
```bash
pip install langextract openpyxl beautifulsoup4 markdownify lxml
```

### 配置 API Key

获取 DeepSeek API Key 并设置环境变量：

**方式 1：临时设置（仅当前会话有效）**
```powershell
# Windows PowerShell
$env:DEEPSEEK_API_KEY="your_api_key_here"
```

```bash
# Linux/Mac
export DEEPSEEK_API_KEY="your_api_key_here"
```

**方式 2：永久设置（推荐）**

创建 `.env` 文件：
```bash
DEEPSEEK_API_KEY=sk-your-api-key-here
```

> 💡 获取 DeepSeek API Key：访问 [https://platform.deepseek.com/](https://platform.deepseek.com/) 注册并创建 API Key

## 📁 项目结构

```
data-extraction/
├── data/                          # 存放政府采购公告HTML文件的目录
│   └── (公告文件夹)/              # 每个文件夹包含一个采购公告的HTML文件
├── extract_with_langextract.py   # 主要的批量提取脚本
├── html_preprocess.py             # HTML预处理和文本转换工具
├── test_chinese.py                # 中文提取测试脚本
├── test_html_preprocess.py        # HTML预处理测试脚本
├── mian.py                        # 示例脚本
└── README.md                      # 项目说明文档
```

## 🎯 使用方法

### 1. 准备数据

将政府采购公告的 HTML 文件放入 `data/` 目录，每个公告应该放在单独的文件夹中：

```
data/
├── 公告1/
│   └── announcement.html
├── 公告2/
│   └── notice.html
└── ...
```

### 2. 运行提取脚本

**测试单个文件**
```bash
python test_html_preprocess.py
```

**批量提取**
```bash
python extract_with_langextract.py
```

### 3. 查看结果

提取结果会保存为：
- **Excel 文件**：`政府采购公告提取结果_YYYYMMDD_HHMMSS.xlsx`
- **CSV 文件**：`政府采购公告提取结果_YYYYMMDD_HHMMSS.csv`
- **JSONL 文件**：`langextract_jsonl/` 目录下

## 📊 提取字段说明

| 字段名称 | 说明 | 示例 |
|---------|------|------|
| 公告时间 | 公告发布的日期时间 | 2024年01月15日 14:30 |
| 项目名称 | 完整的采购项目名称 | XX市政府办公设备采购项目 |
| 采购单位名称 | 发起采购的机构全称 | XX市财政局 |
| 采购单位地址 | 采购单位的详细地址 | XX省XX市XX区XX路123号 |
| 供应商名称 | 中标供应商的全称 | XX科技有限公司 |
| 供应商地址 | 供应商的详细地址 | XX省XX市XX区XX路456号 |
| 中标金额 | 总中标金额 | ¥1,234,567.00元 |
| 采购类别 | 品目类别 | 服务类；货物类 |
| 采购标的 | 具体采购内容 | 办公设备；维护服务 |

## 🔧 配置说明

在 `extract_with_langextract.py` 中可以调整以下配置：

```python
# 模型配置
MODEL_ID = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MODEL_TEMPERATURE = 0  # 低温度让输出更加稳定

# 提取配置
@dataclass
class PipelineConfig:
    input_dir: Path = Path("data")          # 输入目录
    use_custom_model: bool = True           # 使用自定义模型
    extraction_passes: int = 1              # 提取次数
    max_workers: int = 4                    # 并发数
    use_schema_constraints: bool = False    # 使用schema约束
    fail_silently: bool = True              # 静默失败
```

## 🧪 测试

**测试 HTML 预处理**
```bash
python test_html_preprocess.py
```
随机选择一个公告文件夹进行处理，测试 HTML 到文本的转换。

**测试中文提取**
```bash
python test_chinese.py
```
测试 LangExtract 对中文政府采购公告的信息提取能力。

## 📝 核心功能

### HTML 预处理 (`html_preprocess.py`)

- ✅ 自动检测和处理多种中文编码（UTF-8、GB18030、GBK、GB2312）
- ✅ 清理 HTML 标签和无用内容
- ✅ 保留表格结构
- ✅ 转换为纯文本或 Markdown 格式

### 智能提取 (`extract_with_langextract.py`)

- ✅ 使用 DeepSeek 大语言模型进行语义理解
- ✅ Few-shot 学习提升提取准确度
- ✅ 批量处理多个公告
- ✅ 进度条实时显示
- ✅ 错误处理和日志记录
- ✅ 多格式输出（Excel、CSV、JSONL）

## ⚠️ 注意事项

1. **API Key 安全**：不要将 API Key 提交到代码仓库
2. **编码问题**：如遇到乱码，检查 HTML 文件的编码格式
3. **网络问题**：确保能访问 DeepSeek API 服务
4. **数据质量**：提取结果的准确性依赖于公告格式的规范性

## 🐛 常见问题

### Q: 报错 `FeatureNotFound: lxml`
**A:** 安装 lxml 解析器
```bash
pip install lxml
```

### Q: 无法连接 DeepSeek API
**A:** 检查网络连接和 API Key 是否正确设置

### Q: 提取结果不准确
**A:** 可以调整 prompt 或增加 few-shot 示例

### Q: 处理速度慢
**A:** 调整 `max_workers` 参数增加并发数

## 📄 许可证

MIT License

## 👥 贡献

欢迎提交 Issue 和 Pull Request！

## 📧 联系方式

如有问题或建议，请通过 GitHub Issues 联系。

---

⭐ 如果这个项目对您有帮助，请给个 Star！
