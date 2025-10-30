import langextract as lx
from langextract.data import ExampleData, Extraction
from langextract.providers.openai import OpenAILanguageModel
import textwrap
import time

# 1. 定义提取规则 - 中文政府采购信息
prompt = textwrap.dedent("""\
    从政府采购公告中提取关键信息。每个字段类型只提取一次，返回最权威、最完整的值。
    
    **严格约束：**
    1. extraction_text 必须是原文的精确文本片段，逐字逐句复制
    2. **禁止重复提取**：每个 extraction_class 在整个文档中只能出现一次
    3. 如果同一信息出现多次，优先提取标注为"公告信息"或表格开头的权威数据
    4. 不要提取字段标签（如"采购项目名称 |"）、说明文字或页面导航内容
    5. 如果某字段在文档中不存在，完全跳过该字段
    6. 不要返回我提供的案例中的任何信息，提取时只关注输入文本内容。
    
    提取以下9个字段（各提取一次）：
    - 公告时间：公告发布日期时间（YYYY年MM月DD日 HH:MM格式），优先提取"公告时间 |"后的完整时间
    - 项目名称：完整的采购项目名称（优先从"采购项目名称 |"或"二、项目名称："提取）
    - 采购单位名称：发起采购的机构全称（优先从"采购单位 |"提取）
    - 采购单位地址：采购单位完整地址（优先从"采购单位地址 |"提取，需包含门牌号）
    - 供应商名称：排名第一的中标供应商全称（从"三、采购结果"的表格第一行提取）
    - 供应商地址：中标供应商完整地址（从采购结果表格中对应行提取）
    - 中标金额：总中标金额（从"总中标金额 |"提取，需包含货币符号和单位）
    - 采购类别：品目类别（如"服务类"、"货物类"，从主要标的信息部分提取）
    - 采购标的：具体采购内容（从"品目名称"列提取，如"农畜产品批发服务"）
    """)

# 2. 提供高质量的中文示例 - 使用不同类型的采购案例（设备采购）
examples = [
    ExampleData(
        text="""公告信息：
采购项目名称：广州市路灯智能监控系统采购项目
品目：照明设备
采购单位：广州市城市管理局
行政区域：天河区 | 公告时间：2024年01月15日 10:30
总中标金额：￥368.50 万元（人民币）

联系人及联系方式：
项目联系人：李工
采购单位：广州市城市管理局
采购单位地址：广州市天河区天河路123号
代理机构名称：广东采购代理有限公司

三、采购结果
合同包1(智能路灯监控系统)：
供应商名称 | 供应商地址 | 中标金额
深圳智慧照明科技有限公司 | 深圳市南山区科技园南区深南大道9988号 | ￥368.50 万元

四、主要标的信息
合同包1(智能路灯监控系统)：
服务类
品目号 | 品目名称 | 采购标的
1-1 | 照明设备 | 智能路灯监控系统

发布日期：2024年01月15日 10:30""",
        extractions=[
            Extraction(
                extraction_class="公告时间",
                extraction_text="2024年01月15日 10:30",
                attributes={"格式": "日期+时间"}
            ),
            Extraction(
                extraction_class="项目名称",
                extraction_text="广州市路灯智能监控系统采购项目",
                attributes={"类型": "货物采购"}
            ),
            Extraction(
                extraction_class="采购单位名称",
                extraction_text="广州市城市管理局",
                attributes={"性质": "政府部门"}
            ),
            Extraction(
                extraction_class="采购单位地址",
                extraction_text="广州市天河区天河路123号",
                attributes={"区域": "天河区"}
            ),
            Extraction(
                extraction_class="供应商名称",
                extraction_text="深圳智慧照明科技有限公司",
                attributes={"角色": "中标供应商"}
            ),
            Extraction(
                extraction_class="供应商地址",
                extraction_text="深圳市南山区科技园南区深南大道9988号",
                attributes={"区域": "南山区"}
            ),
            Extraction(
                extraction_class="中标金额",
                extraction_text="￥368.50 万元（人民币）",
                attributes={"数值": "3685000.00", "单位": "万元"}
            ),
            Extraction(
                extraction_class="采购类别",
                extraction_text="服务类",
                attributes={"品目": "照明设备"}
            ),
            Extraction(
                extraction_class="采购标的",
                extraction_text="智能路灯监控系统",
                attributes={"类型": "监控设备"}
            ),
        ]
    )
]

# 3. 读取真实的测试文本
with open("test_output.txt", "r", encoding="utf-8") as f:
    input_text = f.read()

# 4. 配置 DeepSeek 模型
MODEL_ID = "deepseek-chat"
API_KEY = "sk-2895a83fa10c49eeb262f6c5139ad423"
BASE_URL = "https://api.deepseek.com"
MODEL_TEMPERATURE = 0.1  # Low temperature keeps output stable
MODEL_FORMAT = lx.data.FormatType.JSON

def configure_model():
    """Return the DeepSeek-backed extraction model."""
    return OpenAILanguageModel(
        model_id=MODEL_ID,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=MODEL_TEMPERATURE,
        format_type=MODEL_FORMAT,
    )


def deduplicate_extractions(document):
    """去重：每个 extraction_class 只保留一个最优结果"""
    if not hasattr(document, 'extractions') or not document.extractions:
        return 0
    
    seen_classes = {}
    deduplicated = []
    
    for ext in document.extractions:
        class_name = ext.extraction_class
        
        # 如果这个类别还没见过，直接添加
        if class_name not in seen_classes:
            seen_classes[class_name] = ext
            deduplicated.append(ext)
        else:
            # 如果已经存在，比较优先级（有 char_interval 且更长的优先）
            existing = seen_classes[class_name]
            
            # 优先选择有明确位置信息的
            if ext.char_interval is not None and existing.char_interval is None:
                # 替换为更好的版本
                deduplicated.remove(existing)
                deduplicated.append(ext)
                seen_classes[class_name] = ext
            elif ext.char_interval is not None and existing.char_interval is not None:
                # 都有位置信息，选择文本更长的（通常更完整）
                if len(ext.extraction_text) > len(existing.extraction_text):
                    deduplicated.remove(existing)
                    deduplicated.append(ext)
                    seen_classes[class_name] = ext
    
    removed_count = len(document.extractions) - len(deduplicated)
    document.extractions = deduplicated
    return removed_count


custom_model = configure_model()

# 记录开始时间
start_time = time.time()

# 5. 执行提取
result = lx.extract(
    text_or_documents=input_text,
    prompt_description=prompt,
    examples=examples,
    model_id="gemini-2.5-flash",
    debug=True,
)

# 记录结束时间
end_time = time.time()
elapsed_time = end_time - start_time

# 后处理：去重
removed_duplicates = deduplicate_extractions(result)
if removed_duplicates > 0:
    print(f"\n🔧 去重处理：移除了 {removed_duplicates} 条重复提取")

# 6. 保存结果
lx.io.save_annotated_documents(
    [result], 
    output_name="extraction_results_chinese.jsonl", 
    output_dir="."
)

# 7. 生成可视化
html_content = lx.visualize("extraction_results_chinese.jsonl")
with open("visualization_chinese.html", "w", encoding="utf-8") as f:
    if hasattr(html_content, 'data'):
        f.write(html_content.data)
    else:
        f.write(html_content)

# 8. 打印结果
print("\n✅ 提取完成!")
print("="*60)
print(f"⏱️  用时: {elapsed_time:.2f} 秒")
print(f"📄 提取结果已保存: extraction_results_chinese.jsonl")
print(f"🎨 可视化文件已生成: visualization_chinese.html")
print("\n🔍 提取的内容:")
print(result)

# 9. 解析并美化输出
if hasattr(result, 'extractions') and result.extractions:
    print("\n" + "="*60)
    print("📊 提取详情:")
    print("="*60)
    for i, ext in enumerate(result.extractions, 1):
        print(f"\n{i}. {ext.extraction_class}")
        print(f"   文本: {ext.extraction_text}")
        print(f"   属性: {ext.attributes}")
