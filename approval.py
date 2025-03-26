import json
import uuid
import psycopg2
import psycopg2.extras
import traceback
from logger import log_info, log_error
import google.generativeai as genai
from pending_to_approved import approve_pending_invoice

API_KEY = "API-KEY"  # Replace with your actual key
genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-1.5-pro-latest")


class InvoiceApproval:
    def __init__(self):
        """Initialize the invoice approval handler with database configuration."""
        self.db_url = "postgresql://neondb_owner:<URL>"
        self.conn = None
        self.cursor = None
        self._connect_db()
        self.departments = {
    0: "None",
    1: "hr",
    2: "logistics",
    3: "it",
}

    def _connect_db(self):
        """Establish a database connection."""
        try:
            self.conn = psycopg2.connect(self.db_url)
            self.cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            log_info("Connected to database successfully")
        except Exception as e:
            log_error(f"Error connecting to database: {str(e)}")
            traceback.print_exc()

    def _ensure_connection(self):
        """Ensure database connection is active, reconnect if needed."""
        if not self.conn or self.conn.closed:
            self._connect_db()
        return self.conn and not self.conn.closed

    def get_invoice_details(self, invoice_id):
        """Retrieve invoice details from the database and extract total amount and items."""
        try:
            query = """SELECT "scanned_data" FROM "InvoiceStore" WHERE "zoho_bill_id" = %s"""
            self.cursor.execute(query, (invoice_id,))
            invoice = self.cursor.fetchone()

            if not invoice:
                log_error(f"Invoice {invoice_id} not found.")
                return None

            scanned_data = invoice["scanned_data"]
            if isinstance(scanned_data, str):  # Convert JSON string to dictionary
                data = json.loads(scanned_data)
            else:
                data = scanned_data  # Already a dictionary

            amount = data.get("total", 0)  # Get total amount
            items = data.get("items", [])  # Get items list

            prompt = f"""
               you are routing invoices to the concerned department. 
               you are given a list of items = {items}
               you need to map this onto one of there departments = {self.departments}
               do not give me any explanation just give me the department as the number
               just a single number nothing else -> just 1, 2, 3. do not show 0
            """
            response = model.generate_content(prompt)
            print("it")
            return {"total_amount": amount, "department": 1}

        except Exception as e:
            log_error(f"Error retrieving invoice: {str(e)}")
            return None

    def process_department_approval(self, invoice_id):
        """Move approval to department-specific employee (Level 1)."""
        try:
            if not self._ensure_connection():
                return
            
            data = self.get_invoice_details(invoice_id)
            # data = {}
            # data['department']=1
            # data['total_amount']=320
            query = """
                SELECT "min_rank_req" FROM "Threshold"
                WHERE "category" = %s 
                AND "max_amount" >= %s
                ORDER BY "max_amount" ASC
                LIMIT 1
            """

            self.cursor.execute(query, (self.departments[data['department']], data['total_amount']))

            threshold = self.cursor.fetchone()
            if not threshold:
                log_error(f"No threshold found for invoice {invoice_id}.")
                return

            min_rank = threshold["min_rank_req"]

            # Find employee with minimum workload in the required role
            query = """
                SELECT "emp_id" FROM "Employee"
                WHERE "role_lvl" = %s
                ORDER BY "workload" ASC, "emp_id" ASC
                LIMIT 1
            """
            self.cursor.execute(query, (min_rank,))

            approver = self.cursor.fetchone()
            if not approver:
                log_error(f"No eligible approver found for invoice {invoice_id}.")
                return

            approver_id = approver["emp_id"]
            approval_id = str(uuid.uuid4())
            # Assign approval to selected employee
            query = """
                INSERT INTO "Approval" ("approval_id", "invoice_id", "emp_id", "created_at", "approval_level", "category")
                VALUES (%s, %s, %s, NOW(), 1, %s)
            """
            self.cursor.execute(query, (approval_id, invoice_id, approver_id, data['department']))

            # Update employee workload
            query = """
                UPDATE "Employee" 
                SET "workload" = "workload" + 1 
                WHERE "emp_id" = %s
            """
            self.cursor.execute(query, (approver_id,))


            self.conn.commit()
            log_info(f"Invoice {invoice_id} assigned to Employee {approver_id} at Level 1.")

        except Exception as e:
            log_error(f"Error processing department approval for invoice {invoice_id}: {str(e)}")
            traceback.print_exc()

    def escalate_approval(self, invoice_id):
        """Move approval to the next superior in the hierarchy."""
        try:
            if not self._ensure_connection():
                return

            # Get last approver and approval level for this invoice
            query = """
                SELECT "emp_id", "approval_level" FROM "Approval"
                WHERE "invoice_id" = %s
                ORDER BY "approval_level" DESC
                LIMIT 1
            """
            self.cursor.execute(query, (invoice_id,))
            last_approval = self.cursor.fetchone()

            if not last_approval:
                log_error(f"No previous approval found for invoice {invoice_id}.")
                return

            last_approver_id = last_approval["emp_id"]
            approval_level = last_approval["approval_level"]

            # Reduce workload of the last approver
            query = """
                UPDATE "Employee" 
                SET "workload" = "workload" - 1 
                WHERE "emp_id" = %s
            """
            self.cursor.execute(query, (last_approver_id,))
            self.conn.commit()

            # If approval level is 2, approvals are done
            if approval_level == 2:
                log_info(f"All approvals are done for invoice {invoice_id}.")
                query = """
                    SELECT "zoho_po_number" FROM "InvoiceStore"
                    WHERE "zoho_bill_id" = %s
                    LIMIT 1
                """
                self.cursor.execute(query, (invoice_id,))
                po_no = self.cursor.fetchone()
                approve_pending_invoice(invoice_id, po_no["zoho_po_number"])
                return

            # Find the superior
            query = """
                SELECT "sup_id", "department" FROM "Employee"
                WHERE "emp_id" = %s
            """
            self.cursor.execute(query, (last_approver_id,))
            superior = self.cursor.fetchone()
            print(superior)
            if not superior or superior["sup_id"] is None:
                log_error(f"No superior found for employee {last_approver_id}.")
                return

            superior_id = superior["sup_id"]
            category = superior["department"]
            print(superior_id, category)
            query = """
                UPDATE "Employee" 
                SET "workload" = "workload" + 1 
                WHERE "emp_id" = %s
            """
            self.cursor.execute(query, (superior_id,))

            self.conn.commit()

            # Assign approval to superior
            approval_id = str(uuid.uuid4())
            query = """
                INSERT INTO "Approval" ("approval_id", "invoice_id", "emp_id", "created_at", "approval_level", "category")
                VALUES (%s, %s, %s, NOW(), %s, %s)
            """
            self.cursor.execute(query, (approval_id, invoice_id, superior_id, approval_level + 1, category))

            self.conn.commit()
            log_info(f"Invoice {invoice_id} escalated to Employee {superior_id}.")

        except Exception as e:
            log_error(f"Error escalating approval for invoice {invoice_id}: {str(e)}")
            traceback.print_exc()
