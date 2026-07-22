import os
import json
import json_repair
from fpdf import FPDF
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_classic.chains.retrieval import create_retrieval_chain
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma

def get_message_text(content) -> str:
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and "text" in part:
                texts.append(part["text"])
        return "".join(texts)
    return str(content)

def extract_json_block(text):
    text = get_message_text(text)
    text = text.strip()
    if text.startswith("```"):
        # find the end of the first line
        first_line_end = text.find("\n")
        if first_line_end != -1:
            text = text[first_line_end:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
            
    # Find start and end of JSON
    start_brace = text.find("{")
    start_bracket = text.find("[")
    
    start_idx = -1
    end_idx = -1
    
    if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
        start_idx = start_brace
        end_idx = text.rfind("}")
    elif start_bracket != -1:
        start_idx = start_bracket
        end_idx = text.rfind("]")
        
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        json_candidate = text[start_idx:end_idx+1]
        try:
            return json_repair.loads(json_candidate)
        except Exception as e:
            print(f"Warning: Failed to parse extracted JSON block with json_repair: {str(e)}")
            
    # Fallback to direct json_repair loads
    return json_repair.loads(text)

def clean_pdf_text(text) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*", # Bullet points
    }
    for search, replace in replacements.items():
        text = text.replace(search, replace)
    return text.encode("latin-1", errors="replace").decode("latin-1")

class ESGReportPDF(FPDF):
    def cell(self, w, h=0, txt="", border=0, ln=0, align="", fill=False, link="", **kwargs):
        txt = clean_pdf_text(txt)
        return super().cell(w, h, txt, border, ln, align, fill, link, **kwargs)

    def multi_cell(self, w, h=0, txt="", border=0, align="J", fill=False, **kwargs):
        txt = clean_pdf_text(txt)
        return super().multi_cell(w, h, txt, border, align, fill, **kwargs)

    def header(self):
        # Draw header band
        self.set_fill_color(30, 41, 59) # Slate-800
        self.rect(0, 0, 210, 25, 'F')
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 12)
        self.set_y(8)
        self.cell(0, 10, 'ENVIRONMENTAL, SOCIAL, & GOVERNANCE (ESG) DISCLOSURE REPORT', 0, 0, 'C')
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(156, 163, 175) # Gray-400
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}} | ESG AI Assistant', 0, 0, 'C')

    def chapter_title(self, label):
        self.set_font('Helvetica', 'B', 14)
        self.set_fill_color(241, 245, 249) # Slate-100
        self.set_text_color(15, 23, 42) # Slate-900
        self.cell(0, 10, f' {label}', 0, 1, 'L', True)
        self.ln(4)

    def _count_wrapped_lines(self, text_str, usable_width):
        lines = text_str.split('\n')
        total_lines = 0
        for line in lines:
            words = line.split(' ')
            if not words or (len(words) == 1 and not words[0]):
                total_lines += 1
                continue
            current_line = ""
            for word in words:
                test_line = current_line + " " + word if current_line else word
                if self.get_string_width(test_line) <= usable_width:
                    current_line = test_line
                else:
                    total_lines += 1
                    current_line = word
            if current_line:
                total_lines += 1
        return max(1, total_lines)

    def table_header(self, col_widths, headers):
        self.set_font('Helvetica', 'B', 10)
        self.set_fill_color(51, 65, 85) # Slate-700
        self.set_text_color(255, 255, 255)
        
        # Calculate required height based on wrap counts
        lines_per_header = []
        for i, header in enumerate(headers):
            usable_w = col_widths[i] - 8 # 2mm padding on each side + cell margins safety buffer
            total_lines = self._count_wrapped_lines(str(header), usable_w)
            lines_per_header.append(total_lines)
            
        max_lines = max(lines_per_header)
        row_height = max_lines * 5.5 + 3
        if row_height < 8:
            row_height = 8
            
        start_x = self.get_x()
        start_y = self.get_y()
        current_x = start_x
        
        self.set_auto_page_break(False)
        for i, header in enumerate(headers):
            # Draw background box and borders first
            self.set_xy(current_x, start_y)
            self.cell(col_widths[i], row_height, "", border=1, fill=True)
            
            # Position and draw multi-line text inside the box
            self.set_xy(current_x + 2, start_y + (row_height - (lines_per_header[i] * 4.5)) / 2)
            self.multi_cell(col_widths[i] - 4, 4.5, str(header), border=0, align='C')
            current_x += col_widths[i]
            
        self.set_auto_page_break(True, margin=15)
        self.set_xy(start_x, start_y + row_height)

    def table_row(self, col_widths, data, row_index):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(71, 85, 105) # Slate-600
        if row_index % 2 == 0:
            self.set_fill_color(248, 250, 252) # Slate-50
        else:
            self.set_fill_color(255, 255, 255)
            
        # 1. Calculate required height based on wrap counts
        lines_per_cell = []
        for i, val in enumerate(data):
            usable_w = col_widths[i] - 8 # 2mm padding on each side + cell margins safety buffer
            total_lines = self._count_wrapped_lines(str(val), usable_w)
            lines_per_cell.append(total_lines)
            
        max_lines = max(lines_per_cell)
        row_height = max_lines * 5.5 + 3
        if row_height < 8:
            row_height = 8
            
        # 2. Check manual page break
        if self.get_y() + row_height > (self.h - self.b_margin):
            self.add_page()
            
        # 3. Render each cell in the row (temporarily disable auto-page breaks)
        start_x = self.get_x()
        start_y = self.get_y()
        current_x = start_x
        
        self.set_auto_page_break(False)
        for i, val in enumerate(data):
            # Draw background box and borders first
            self.set_xy(current_x, start_y)
            self.cell(col_widths[i], row_height, "", border=1, fill=True)
            
            # Position and draw multi-line text inside the box
            self.set_xy(current_x + 2, start_y + (row_height - (lines_per_cell[i] * 4.5)) / 2)
            self.multi_cell(col_widths[i] - 4, 4.5, str(val), border=0, align='L')
            current_x += col_widths[i]
            
        self.set_auto_page_break(True, margin=15)
        self.set_xy(start_x, start_y + row_height)


def generate_report_json(requestId: str, module: str = "basic", model: str = "llama3") -> dict:
    print(f"Generating formatted ESG report JSON for request {requestId} using module {module} and model {model}")
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    chroma_dir = os.path.join(base_dir, "rag_chroma_db", f"{requestId}_{model}")

    if not os.path.exists(chroma_dir):
        print(f"Vector store not found at {chroma_dir}. Rebuilding dynamically...")
        from app.ingest.ingest_docs import ingest_docs_for_request
        success = ingest_docs_for_request(requestId, model=model)
        if not success:
            raise ValueError(f"Failed to dynamically build vector store at {chroma_dir}")

    # 1. Load Chroma with appropriate embedding class
    from app.core.models import get_model_provider
    provider = get_model_provider(model)
    embeddings = provider.get_embeddings()

    db = Chroma(persist_directory=chroma_dir, embedding_function=embeddings)
    retriever = db.as_retriever(search_kwargs={"k": 12})
    
    llm = provider.get_llm(temperature=0.0)

    # 2. Extract raw facts from context
    raw_extraction_prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert ESG data extraction assistant.
Extract all ESG performance facts, values, percentages, metrics, and policies mentioned in the retrieved context.
Format the output as a raw JSON with these categories: company_details, environmental_performance, social_indicators, governance_compliance, findings, recommendations.
Include specific numbers, units (like kWh, m3, tonnes), policies, and metrics.
If a value is not in the context, mark it as null.
Return ONLY valid raw JSON without code fences or extra text."""),
        ("human", "Extract facts from the following context:\n\n{context}\n\nInput Request: Extract all company info, electricity, natural gas, water consumption, waste, Scope 1/2/3, employees counts (total, permanent, temporary, male, female), training hours, workplace accidents, policies, findings, and suggestions.")
    ])

    question_answer_chain = create_stuff_documents_chain(llm, raw_extraction_prompt)
    rag_chain = create_retrieval_chain(retriever, question_answer_chain)
    
    response = rag_chain.invoke({"input": "Extract all ESG details"})
    raw_answer = response.get("answer", "").strip()

    try:
        raw_json = extract_json_block(raw_answer)
    except Exception as e:
        print(f"Warning: Failed to parse raw ESG JSON: {str(e)}")
        raw_json = {"raw_text": raw_answer}

    # 3. Transform using report.txt prompt format
    prompt_path = os.path.join(base_dir, "prompts", "report.txt")
    if not os.path.exists(prompt_path):
        raise FileNotFoundError(f"report.txt prompt template not found at {prompt_path}")

    with open(prompt_path, "r", encoding="utf-8") as f:
        report_template = f.read()

    # Inject input JSON and module constraints
    module_instructions = ""
    if module == "basic":
        module_instructions = """
## Basic Report Constraints
You are generating a BASIC ESG report. Focus on essential core metrics. Extract all available metrics mentioned in the facts context across environment, social, and governance. If a metric is not present in the facts, mark it as null.
"""
    else:
        module_instructions = """
## Comprehensive Report Requirements
You are generating a COMPREHENSIVE ESG report. Please extract and populate all available metrics across environment, social, and governance.
"""

    report_template = report_template.replace("Return ONLY the transformed JSON.", f"{module_instructions}\n\nReturn ONLY the transformed JSON.")
    final_prompt_text = report_template.replace("{{INPUT_JSON}}", json.dumps(raw_json, indent=2))
    
    # Invoke model
    formatted_response = llm.invoke(final_prompt_text)

    try:
        final_report_json = extract_json_block(formatted_response.content)
    except Exception as e:
        print(f"Error parsing final formatted ESG report: {str(e)}")
        content_str = get_message_text(formatted_response.content)
        # Return fallback structure
        final_report_json = {
            "company": {"name": "Unknown", "reportingYear": "Unknown"},
            "executiveSummary": "Failed to compile report: " + content_str,
            "environment": {},
            "social": {},
            "governance": {},
            "findings": [],
            "recommendations": []
        }

    # Automatically enrich generated JSON with database questionnaire facts if available
    try:
        from db.session import SessionLocal
        from sqlalchemy import text
        from app.core.utils import ReportUtility

        db_session = SessionLocal()
        try:
            try:
                num_id = int(str(requestId).replace("req_", ""))
            except ValueError:
                num_id = 0
            if num_id:
                db_row = db_session.execute(
                    text("SELECT report_data FROM upload_request WHERE request_id = :req_id"),
                    {"req_id": num_id}
                ).fetchone()
                if db_row and db_row.report_data:
                    import json as py_json
                    parsed_db_data = py_json.loads(db_row.report_data)
                    if isinstance(parsed_db_data, list):
                        final_report_json = ReportUtility.enrich_report_json_from_db(final_report_json, parsed_db_data)
                    elif isinstance(parsed_db_data, dict) and "questionnaire_data" in parsed_db_data:
                        final_report_json = ReportUtility.enrich_report_json_from_db(final_report_json, parsed_db_data["questionnaire_data"])
        finally:
            db_session.close()
    except Exception as enrich_err:
        print(f"Warning: Automatic report JSON enrichment failed: {enrich_err}")

    return final_report_json


def format_value(val):
    if val is None or val == "" or str(val).lower() == "null" or str(val).lower() == "none":
        return "Not Disclosed"
    return str(val)


def create_pdf_from_json(report_json: dict, output_path: str):
    pdf = ESGReportPDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title Page/Section Header - Company Summary
    company = report_json.get("company", {})
    pdf.set_font('Helvetica', 'B', 16)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, f'ESG Performance Disclosure Report', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 5, f'Generated on behalf of {format_value(company.get("name"))} | Reporting Year: {format_value(company.get("reportingYear"))}', 0, 1, 'L')
    pdf.ln(6)

    # Render Company Meta Info Table
    col_widths = [50, 140]
    metadata = [
        ("Company Name", format_value(company.get("name"))),
        ("Industry Sector", format_value(company.get("industry"))),
        ("Primary Location", format_value(company.get("location"))),
        ("Total Employees", format_value(company.get("employees"))),
    ]
    pdf.set_font('Helvetica', 'B', 10)
    for idx, (label, val) in enumerate(metadata):
        pdf.table_row(col_widths, [label, val], idx)
    pdf.ln(8)

    # Executive Summary Section
    pdf.chapter_title('Executive Summary')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    summary_text = report_json.get("executiveSummary", "No executive summary available.")
    pdf.multi_cell(0, 6, summary_text)
    pdf.ln(8)

    # Environment Section
    pdf.chapter_title('1. Environmental Stewardship')
    env = report_json.get("environment", {})
    
    # 1.1 Resource Consumption Table
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(51, 65, 85)
    pdf.cell(0, 8, 'Resource & Energy Consumption', 0, 1, 'L')
    pdf.ln(2)
    
    col_widths_env = [60, 65, 65]
    pdf.table_header(col_widths_env, ['Utility / Resource', 'Consumption Value', 'Unit'])
    
    utilities = [
        ("Electricity", env.get("electricity", {})),
        ("Natural Gas", env.get("naturalGas", {})),
        ("Water", env.get("water", {}))
    ]
    
    for idx, (name, val_dict) in enumerate(utilities):
        consumption = format_value(val_dict.get("consumption") if isinstance(val_dict, dict) else None)
        unit = format_value(val_dict.get("unit") if isinstance(val_dict, dict) else None)
        pdf.table_row(col_widths_env, [name, consumption, unit], idx)
    pdf.ln(6)

    # 1.2 Waste Management & Emissions Table
    pdf.cell(0, 8, 'Waste Management & Greenhouse Gas Emissions', 0, 1, 'L')
    pdf.ln(2)
    
    waste = env.get("waste", {})
    waste_gen = format_value(waste.get("generated") if isinstance(waste, dict) else None)
    waste_unit = format_value(waste.get("unit") if isinstance(waste, dict) else None)
    recycled = format_value(waste.get("recycledPercentage") if isinstance(waste, dict) else None)
    if recycled != "Not Disclosed":
        recycled = f"{recycled}%"
        
    scope1 = env.get("scope1", {})
    scope2 = env.get("scope2", {})
    scope3 = env.get("scope3", {})
    
    s1_val = format_value(scope1.get("value") if isinstance(scope1, dict) else None)
    s2_val = format_value(scope2.get("value") if isinstance(scope2, dict) else None)
    s3_val = format_value(scope3.get("value") if isinstance(scope3, dict) else None)

    env_metrics = [
        ("Waste Generated", f"{waste_gen} {waste_unit}" if waste_gen != "Not Disclosed" else "Not Disclosed"),
        ("Waste Recycled Percentage", recycled),
        ("Scope 1 Direct Emissions", s1_val),
        ("Scope 2 Indirect Emissions", s2_val),
        ("Scope 3 Value-Chain Emissions", s3_val),
    ]
    
    pdf.table_header(col_widths, ['Metric Indicator', 'Extracted Value'])
    for idx, (label, val) in enumerate(env_metrics):
        pdf.table_row(col_widths, [label, val], idx)
    pdf.ln(8)

    # Social Section
    pdf.chapter_title('2. Social & Workforce Characteristics')
    social = report_json.get("social", {})
    emp = social.get("employees", {})
    
    emp_total = format_value(emp.get("total") if isinstance(emp, dict) else None)
    emp_perm = format_value(emp.get("permanent") if isinstance(emp, dict) else None)
    emp_temp = format_value(emp.get("temporary") if isinstance(emp, dict) else None)
    emp_male = format_value(emp.get("male") if isinstance(emp, dict) else None)
    emp_female = format_value(emp.get("female") if isinstance(emp, dict) else None)
    
    training = format_value(social.get("trainingHours"))
    accidents = format_value(social.get("workplaceAccidents"))
    
    social_metrics = [
        ("Total Workforce Count", emp_total),
        ("Permanent Staff", emp_perm),
        ("Temporary / Subcontract Staff", emp_temp),
        ("Male Representation", emp_male),
        ("Female Representation", emp_female),
        ("Average Employee Training Hours", training),
        ("Occupational Workplace Accidents", accidents),
    ]
    
    pdf.table_header(col_widths, ['Workforce Performance Indicator', 'Disclosed Value'])
    for idx, (label, val) in enumerate(social_metrics):
        pdf.table_row(col_widths, [label, val], idx)
    pdf.ln(6)

    # Social Policies
    policies = social.get("policies", [])
    if policies:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, 'Disclosed Social Policies:', 0, 1, 'L')
        pdf.set_font('Helvetica', '', 10)
        for policy in policies:
            pdf.cell(10, 6, chr(149), 0, 0, 'C')
            pdf.cell(0, 6, str(policy), 0, 1, 'L')
        pdf.ln(6)
    pdf.ln(4)

    # Governance Section
    pdf.chapter_title('3. Governance & Business Integrity')
    gov = report_json.get("governance", {})
    
    supplier = "Yes" if gov.get("supplierSustainability") is True else ("No" if gov.get("supplierSustainability") is False else "Not Disclosed")
    data_prot = "Yes" if gov.get("dataProtection") is True else ("No" if gov.get("dataProtection") is False else "Not Disclosed")
    anti_corr = "Yes" if gov.get("antiCorruption") is True else ("No" if gov.get("antiCorruption") is False else "Not Disclosed")
    
    gov_metrics = [
        ("Supplier Sustainability Screening", supplier),
        ("Formal Data Protection Policy", data_prot),
        ("Anti-Corruption & Anti-Bribery Controls", anti_corr)
    ]
    
    pdf.table_header(col_widths, ['Governance Indicators & Compliance Check', 'Status'])
    for idx, (label, val) in enumerate(gov_metrics):
        pdf.table_row(col_widths, [label, val], idx)
    pdf.ln(6)
    
    gov_policies = gov.get("policies", [])
    if gov_policies:
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(0, 6, 'Disclosed Governance Policies:', 0, 1, 'L')
        pdf.set_font('Helvetica', '', 10)
        for policy in gov_policies:
            pdf.cell(10, 6, chr(149), 0, 0, 'C')
            pdf.cell(0, 6, str(policy), 0, 1, 'L')
        pdf.ln(6)
    pdf.ln(4)

    # Findings & Recommendations Section
    pdf.chapter_title('4. Observations, Findings & Suggestions')
    
    findings = report_json.get("findings", [])
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'Key ESG Findings:', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    pdf.set_text_color(51, 65, 85)
    if findings:
        for finding in findings:
            left_margin = pdf.l_margin
            pdf.set_x(left_margin)
            pdf.cell(10, 6, chr(149), 0, 0, 'C')
            pdf.set_left_margin(left_margin + 10)
            pdf.multi_cell(0, 6, str(finding))
            pdf.set_left_margin(left_margin)
    else:
        pdf.cell(0, 6, 'No specific negative ESG findings or gaps observed.', 0, 1, 'L')
    pdf.ln(4)
    
    recs = report_json.get("recommendations", [])
    pdf.set_font('Helvetica', 'B', 11)
    pdf.cell(0, 8, 'Identified Gaps:', 0, 1, 'L')
    pdf.set_font('Helvetica', '', 10)
    if recs:
        for rec in recs:
            left_margin = pdf.l_margin
            pdf.set_x(left_margin)
            pdf.cell(10, 6, chr(149), 0, 0, 'C')
            pdf.set_left_margin(left_margin + 10)
            pdf.multi_cell(0, 6, str(rec))
            pdf.set_left_margin(left_margin)
    else:
        pdf.cell(0, 6, 'No immediate actions or recommendations listed.', 0, 1, 'L')

    pdf.output(output_path)
    print(f"PDF report successfully saved to {output_path}")
