import re

class ReportUtility:
    @staticmethod
    def enrich_report_json_from_db(report_json: dict, report_data_list: list, request_id: str = None) -> dict:
        """
        Enriches the LLM-generated structured report JSON with verified questionnaire metrics 
        from the database (report_data_list) when those fields are null or missing.
        """
        if not isinstance(report_json, dict) or not isinstance(report_data_list, list):
            return report_json
            
        # Helper to find answer by keywords in question
        def find_val(keywords, exclude_keywords=None):
            for item in report_data_list:
                if not isinstance(item, dict):
                    continue
                q = item.get("question", "").lower()
                ans = item.get("answer", "")
                if ans and str(ans).lower() != "missing" and str(ans).lower() != "not specified":
                    if all(kw in q for kw in keywords):
                        if exclude_keywords and any(ex in q for ex in exclude_keywords):
                            continue
                        return ans
            return None
            
        # Helper to parse number from string (e.g. "180 employees" -> 180, "1,240,000 kWh" -> 1240000)
        def parse_number(val, suffix_keywords=None):
            import re
            if val is None:
                return None
            try:
                cleaned_val = str(val).replace(",", "")
                if suffix_keywords:
                    for suffix in suffix_keywords:
                        match = re.search(r'(\d+(?:\.\d+)?)\s*' + re.escape(suffix), cleaned_val, re.IGNORECASE)
                        if match:
                            num_str = match.group(1)
                            return int(float(num_str)) if "." not in num_str else float(num_str)
                nums = re.findall(r'\d+(?:\.\d+)?', cleaned_val)
                if nums:
                    return int(float(nums[0])) if "." not in nums[0] else float(nums[0])
            except Exception:
                pass
            return None

        # Enrich Company details
        if "company" not in report_json:
            report_json["company"] = {}
        
        comp = report_json["company"]
        if comp.get("employees") is None or str(comp.get("employees")).lower() in ["none", "null", ""]:
            emp_ans = find_val(["total employees"]) or find_val(["how many employees"])
            if emp_ans:
                comp["employees"] = parse_number(emp_ans) or emp_ans
                
        # Enrich Social employees split
        if "social" not in report_json:
            report_json["social"] = {}
        social = report_json["social"]
        if "employees" not in social:
            social["employees"] = {}
            
        emp = social["employees"]
        
        # Female employees
        if emp.get("female") is None or str(emp.get("female")).lower() in ["none", "null", ""]:
            val = find_val(["female employees"]) or find_val(["female", "employee"])
            if val:
                emp["female"] = parse_number(val) or val
                
        # Male employees
        if emp.get("male") is None or str(emp.get("male")).lower() in ["none", "null", ""]:
            val = find_val(["male employees"], exclude_keywords=["female"]) or find_val(["male", "employee"], exclude_keywords=["female"])
            if val:
                emp["male"] = parse_number(val) or val
                
        # Permanent employees
        if emp.get("permanent") is None or str(emp.get("permanent")).lower() in ["none", "null", ""]:
            val = find_val(["permanent employees"]) or find_val(["permanent", "employee"])
            if val:
                emp["permanent"] = parse_number(val) or val
                
        # Temporary employees
        if emp.get("temporary") is None or str(emp.get("temporary")).lower() in ["none", "null", ""]:
            val = find_val(["temporary employees"]) or find_val(["temporary", "employee"])
            if val:
                emp["temporary"] = parse_number(val) or val

        # Total employees in social
        if emp.get("total") is None or emp.get("total") == 0 or str(emp.get("total")).lower() in ["none", "null", ""]:
            val = find_val(["total employees"]) or find_val(["how many employees"])
            if val:
                emp["total"] = parse_number(val) or val

        # Workplace accidents
        if social.get("workplaceAccidents") is None or str(social.get("workplaceAccidents")).lower() in ["none", "null", ""]:
            val = find_val(["workplace accidents"]) or find_val(["accidents"])
            if val:
                social["workplaceAccidents"] = parse_number(val) if parse_number(val) is not None else 0

        # Incidents
        doc_incidents = None
        if request_id:
            import os, docx
            req_str = str(request_id)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "documents", req_str if req_str.startswith("req_") else f"req_{req_str}"))
            if os.path.exists(base_dir):
                for f in os.listdir(base_dir):
                    if "incident" in f.lower() and f.endswith(".docx"):
                        filepath = os.path.join(base_dir, f)
                        try:
                            doc = docx.Document(filepath)
                            count = 0
                            for table in doc.tables:
                                for row in table.rows:
                                    cells = [c.text.strip() for c in row.cells]
                                    if len(cells) >= 2 and (cells[0].lower().startswith("hr-") or cells[0].lower().startswith("inc-") or "2026-" in cells[0]):
                                        count += 1
                            if count > 0:
                                doc_incidents = count
                        except Exception:
                            pass

        if doc_incidents is not None:
            social["incidents"] = doc_incidents
        elif social.get("incidents") is None or str(social.get("incidents")).lower() in ["none", "null", ""]:
            val = find_val(["incidents occurred"]) or find_val(["environmental incidents"]) or find_val(["incidents"])
            if val:
                parsed_inc = parse_number(val)
                social["incidents"] = parsed_inc if parsed_inc is not None else (0 if "no" in str(val).lower() or "zero" in str(val).lower() else 1)
            else:
                social["incidents"] = 0
                
        # Training hours
        th = social.get("trainingHours")
        if th is not None and th != "" and str(th).lower() not in ["none", "null"]:
            parsed_hours = parse_number(th, suffix_keywords=["hours", "hrs"])
            if parsed_hours is not None:
                social["trainingHours"] = parsed_hours
        else:
            val = find_val(["training hours"]) or find_val(["training"])
            if val:
                parsed_hours = parse_number(val, suffix_keywords=["hours", "hrs"])
                if parsed_hours is not None:
                    social["trainingHours"] = parsed_hours
                else:
                    social["trainingHours"] = val

        # Enrich Environment
        if "environment" not in report_json:
            report_json["environment"] = {}
        env = report_json["environment"]
        
        # electricity
        if "electricity" not in env:
            env["electricity"] = {}
        elec = env["electricity"]
        if elec.get("consumption") is None or str(elec.get("consumption")).lower() in ["none", "null", ""]:
            val = find_val(["electricity consumed"]) or find_val(["electricity"])
            if val:
                elec["consumption"] = parse_number(val) or val
                elec["unit"] = "kWh" if "kwh" in str(val).lower() else "MWh"

        # Parse monthly electricity consumption
        if not elec.get("monthlyElectricityConsumption") or len(elec.get("monthlyElectricityConsumption")) == 0:
            month_val = find_val(["monthly report"]) or find_val(["monthly electricity"]) or find_val(["electricity", "jan"])
            if month_val:
                import re
                months_data = []
                pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\d]*([\d,]+)(?:\s*kWh)?(?:\s*\(([\d\.]+)%\)?)?"
                for m in re.finditer(pattern, str(month_val), re.IGNORECASE):
                    month = m.group(1).capitalize()
                    cons = int(m.group(2).replace(",", ""))
                    ren = float(m.group(3)) if m.group(3) else None
                    item = {"month": month, "consumption": cons}
                    if ren is not None:
                        item["renewablePercentage"] = ren
                    months_data.append(item)
                if months_data:
                    elec["monthlyElectricityConsumption"] = months_data
                
        # naturalGas
        if "naturalGas" not in env:
            env["naturalGas"] = {}
        gas = env["naturalGas"]
        if gas.get("consumption") is None or str(gas.get("consumption")).lower() in ["none", "null", ""]:
            val = find_val(["natural gas consumed"]) or find_val(["natural gas"])
            unit_str = None
            if not val:
                # Fallback to parsing from "Total fuel consumed" question
                fuel_val = find_val(["fuel", "consumed"]) or find_val(["fuel", "consumption"])
                if fuel_val:
                    import re
                    cleaned_fuel = str(fuel_val).replace(",", "")
                    match = re.search(r'(?:natural\s+)?gas(?:[^\d]*?)(\d+(?:\.\d+)?)\s*(\w+)?', cleaned_fuel, re.IGNORECASE)
                    if match:
                        num_str = match.group(1)
                        parsed_val = int(float(num_str)) if "." not in num_str else float(num_str)
                        val = str(parsed_val)
                        unit_str = match.group(2)
                    else:
                        match = re.search(r'(\d+(?:\.\d+)?)\s*(\w+)?(?:[^\w]*?)(?:natural\s+)?gas', cleaned_fuel, re.IGNORECASE)
                        if match:
                            num_str = match.group(1)
                            parsed_val = int(float(num_str)) if "." not in num_str else float(num_str)
                            val = str(parsed_val)
                            unit_str = match.group(2)
            if val:
                gas["consumption"] = parse_number(val) or val
                gas["unit"] = unit_str if unit_str else ("kWh" if "kwh" in str(val).lower() else "m3")

        # water
        if "water" not in env:
            env["water"] = {}
        wat = env["water"]
        if wat.get("consumption") is None or str(wat.get("consumption")).lower() in ["none", "null", ""]:
            val = find_val(["water consumption"]) or find_val(["water consumed"])
            if val:
                wat["consumption"] = parse_number(val) or val
                wat["unit"] = "m3"

        # Parse monthly water consumption
        existing_water = wat.get("monthlyWaterConsumption") or []
        is_water_invalid = any((item.get("withdrawn") or 0) > 10000 for item in existing_water) or len(existing_water) < 12

        if is_water_invalid:
            water_months = []
            # Try loading directly from document files if request_id is available
            if request_id:
                import os, docx
                req_str = str(request_id)
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "documents", req_str if req_str.startswith("req_") else f"req_{req_str}"))
                if os.path.exists(base_dir):
                    for f in os.listdir(base_dir):
                        if "water" in f.lower() and f.endswith(".docx"):
                            filepath = os.path.join(base_dir, f)
                            try:
                                doc = docx.Document(filepath)
                                for table in doc.tables:
                                    for row in table.rows:
                                        cells = [c.text.strip() for c in row.cells]
                                        if len(cells) >= 4 and cells[0] in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
                                            try:
                                                m = cells[0]
                                                w = int(cells[1].replace(",", ""))
                                                c = int(cells[2].replace(",", ""))
                                                r = int(cells[3].replace(",", ""))
                                                d = int(cells[4].replace(",", "")) if len(cells) > 4 else 0
                                                water_months.append({"month": m, "withdrawn": w, "consumption": c, "recycled": r, "discharged": d})
                                            except Exception:
                                                pass
                            except Exception:
                                pass

            if water_months and len(water_months) == 12:
                wat["monthlyWaterConsumption"] = water_months
            else:
                month_water_val = find_val(["monthly water"]) or find_val(["water", "jan"])
                if month_water_val:
                    import re
                    w_months = []
                    pattern = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[^\d]*([\d,]+)[^\d]+([\d,]+)[^\d]+([\d,]+)"
                    for m in re.finditer(pattern, str(month_water_val), re.IGNORECASE):
                        month = m.group(1).capitalize()
                        w = int(m.group(2).replace(",", ""))
                        c = int(m.group(3).replace(",", ""))
                        r = int(m.group(4).replace(",", ""))
                        w_months.append({"month": month, "withdrawn": w, "consumption": c, "recycled": r})
                    if w_months:
                        wat["monthlyWaterConsumption"] = w_months

        # waste
        if "waste" not in env:
            env["waste"] = {}
        wst = env["waste"]
        if wst.get("generated") is None or str(wst.get("generated")).lower() in ["none", "null", ""]:
            val = find_val(["waste generated"]) or find_val(["total waste"]) or find_val(["waste"])
            if val:
                wst["generated"] = parse_number(val) or val
                wst["unit"] = "tonnes" if "tonne" in str(val).lower() else "kg"
        if wst.get("recycledPercentage") is None or str(wst.get("recycledPercentage")).lower() in ["none", "null", ""]:
            val = find_val(["recycled"]) or find_val(["waste recycled"])
            if val:
                parsed_pct = parse_number(val)
                if parsed_pct is not None:
                    wst["recycledPercentage"] = parsed_pct
                
        # Scope 1
        if "scope1" not in env:
            env["scope1"] = {}
        s1 = env["scope1"]
        if s1.get("value") is None or str(s1.get("value")).lower() in ["none", "null", ""]:
            val = find_val(["scope 1"]) or find_val(["scope1"]) or find_val(["direct emissions"])
            if val:
                s1["value"] = val
                s1["status"] = s1.get("status") or "Reported"
        elif s1.get("value") and not s1.get("status"):
            s1["status"] = "Reported"
                
        # Scope 2
        if "scope2" not in env:
            env["scope2"] = {}
        s2 = env["scope2"]
        if s2.get("value") is None or str(s2.get("value")).lower() in ["none", "null", ""]:
            val = find_val(["scope 2"]) or find_val(["scope2"]) or find_val(["location-based"]) or find_val(["indirect emissions"])
            if val:
                s2["value"] = val
                s2["status"] = s2.get("status") or "Reported"
        elif s2.get("value") and not s2.get("status"):
            s2["status"] = "Reported"

        # Scope 3
        if "scope3" not in env:
            env["scope3"] = {}
        s3 = env["scope3"]
        if s3.get("value") is None or str(s3.get("value")).lower() in ["none", "null", ""]:
            val = find_val(["scope 3"]) or find_val(["scope3"]) or find_val(["value-chain emissions"])
            if val:
                s3["value"] = val
                s3["status"] = s3.get("status") or "Reported"
        elif s3.get("value") and not s3.get("status"):
            s3["status"] = "Reported"

        # Enrich Governance Policies
        if "governance" not in report_json:
            report_json["governance"] = {}
        gov = report_json["governance"]
        
        if gov.get("antiCorruption") is None or str(gov.get("antiCorruption")).lower() in ["none", "null", ""]:
            val = find_val(["anti-corruption policy"]) or find_val(["anti-corruption"])
            if val:
                gov["antiCorruption"] = "yes" in str(val).lower() or "true" in str(val).lower()
                
        if gov.get("supplierSustainability") is None or str(gov.get("supplierSustainability")).lower() in ["none", "null", ""]:
            val = find_val(["supplier sustainability"]) or find_val(["supplier code of conduct"])
            if val:
                gov["supplierSustainability"] = "yes" in str(val).lower() or "true" in str(val).lower()

        return report_json
