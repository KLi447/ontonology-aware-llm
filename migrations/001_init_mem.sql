CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE SCHEMA IF NOT EXISTS domain;

CREATE TABLE IF NOT EXISTS domain.customers (
  customer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  industry TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS domain.sales_orders (
  so_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID NOT NULL REFERENCES domain.customers(customer_id) ON DELETE CASCADE,
  so_number TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft','approved','in_fulfillment','fulfilled','cancelled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS domain.work_orders (
  wo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  so_id UUID NOT NULL REFERENCES domain.sales_orders(so_id) ON DELETE CASCADE,
  description TEXT,
  status TEXT NOT NULL CHECK (status IN ('queued','in_progress','blocked','done')),
  technician TEXT,
  scheduled_for DATE
);

CREATE TABLE IF NOT EXISTS domain.invoices (
  invoice_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  so_id UUID NOT NULL REFERENCES domain.sales_orders(so_id) ON DELETE CASCADE,
  invoice_number TEXT UNIQUE NOT NULL,
  amount NUMERIC(12,2) NOT NULL,
  due_date DATE NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open','paid','void')),
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS domain.payments (
  payment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id UUID NOT NULL REFERENCES domain.invoices(invoice_id) ON DELETE CASCADE,
  amount NUMERIC(12,2) NOT NULL,
  method TEXT,
  paid_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS domain.tasks (
  task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  customer_id UUID REFERENCES domain.customers(customer_id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  body TEXT,
  status TEXT NOT NULL CHECK (status IN ('todo','doing','done')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


INSERT INTO domain.customers (name, industry, notes) VALUES
('Acme Manufacturing', 'Manufacturing', 'Key industrial client with recurring orders.'),
('Northwind Traders', 'Wholesale', 'Often requests bulk orders of seasonal products.'),
('Globex Corporation', 'Technology', 'Focuses on R&D equipment.'),
('Initech', 'Software', 'Occasional consulting and hardware setup.'),
('Umbrella Health', 'Healthcare', 'Medical equipment and device calibration.'),
('Soylent Foods', 'Food & Beverage', 'High volume shipments, strict fulfillment deadlines.')
ON CONFLICT DO NOTHING;

INSERT INTO domain.sales_orders (customer_id, so_number, title, status)
SELECT customer_id, so_number, title, status FROM (
  VALUES
    ((SELECT customer_id FROM domain.customers WHERE name='Acme Manufacturing'), 'SO-1001', 'Industrial Fan Assembly', 'in_fulfillment'),
    ((SELECT customer_id FROM domain.customers WHERE name='Northwind Traders'), 'SO-1002', 'Winter Promo Bulk Order', 'approved'),
    ((SELECT customer_id FROM domain.customers WHERE name='Globex Corporation'), 'SO-1003', 'Lab Testing Kit Batch 7', 'fulfilled'),
    ((SELECT customer_id FROM domain.customers WHERE name='Initech'), 'SO-1004', 'Server Rack Installation', 'draft'),
    ((SELECT customer_id FROM domain.customers WHERE name='Umbrella Health'), 'SO-1005', 'Ultrasound Maintenance Contract', 'in_fulfillment'),
    ((SELECT customer_id FROM domain.customers WHERE name='Soylent Foods'), 'SO-1006', 'Nutrient Mix Plant Upgrade', 'approved')
) AS t(customer_id, so_number, title, status)
ON CONFLICT DO NOTHING;

INSERT INTO domain.work_orders (so_id, description, status, technician, scheduled_for)
SELECT so_id, description, status, technician, scheduled_for FROM (
  VALUES
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1001'), 'Assemble fan components', 'in_progress', 'Jordan Smith', DATE '2025-10-09'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1001'), 'Perform quality check', 'queued', 'Priya Patel', DATE '2025-10-10'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1002'), 'Prepare shipment packaging', 'queued', 'Alex Chen', DATE '2025-10-12'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1003'), 'Final product inspection', 'done', 'Maria Gonzalez', DATE '2025-09-28'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1005'), 'Calibrate ultrasound machines', 'blocked', 'David Lee', DATE '2025-10-15')
) AS t(so_id, description, status, technician, scheduled_for)
ON CONFLICT DO NOTHING;

INSERT INTO domain.invoices (so_id, invoice_number, amount, due_date, status)
SELECT so_id, invoice_number, amount, due_date, status FROM (
  VALUES
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1001'), 'INV-5001', 12500.00, DATE '2025-10-30', 'open'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1002'), 'INV-5002', 8600.00, DATE '2025-11-10', 'open'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1003'), 'INV-5003', 10250.00, DATE '2025-09-30', 'paid'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1004'), 'INV-5004', 4200.00, DATE '2025-11-05', 'void'),
    ((SELECT so_id FROM domain.sales_orders WHERE so_number='SO-1005'), 'INV-5005', 17900.00, DATE '2025-10-28', 'open')
) AS t(so_id, invoice_number, amount, due_date, status)
ON CONFLICT DO NOTHING;

INSERT INTO domain.payments (invoice_id, amount, method, paid_at)
SELECT invoice_id, amount, method, paid_at FROM (
  VALUES
    ((SELECT invoice_id FROM domain.invoices WHERE invoice_number='INV-5003'), 10250.00, 'wire_transfer', DATE '2025-09-29T14:23:00Z'),
    ((SELECT invoice_id FROM domain.invoices WHERE invoice_number='INV-5002'), 4000.00, 'credit_card', DATE '2025-10-06T11:00:00Z')
) AS t(invoice_id, amount, method, paid_at)
ON CONFLICT DO NOTHING;

INSERT INTO domain.tasks (customer_id, title, body, status)
SELECT customer_id, title, body, status FROM (
  VALUES
    ((SELECT customer_id FROM domain.customers WHERE name='Acme Manufacturing'),
     'Follow up on QA issues',
     'Reach out to QA team about recurring vibration reports in fan assembly.',
     'doing'),
    ((SELECT customer_id FROM domain.customers WHERE name='Northwind Traders'),
     'Confirm packaging specs',
     'Customer needs updated pallet configuration before shipping.',
     'todo'),
    ((SELECT customer_id FROM domain.customers WHERE name='Globex Corporation'),
     'Prepare renewal proposal',
     'Draft new maintenance contract proposal for Q1 2026.',
     'todo'),
    ((SELECT customer_id FROM domain.customers WHERE name='Umbrella Health'),
     'Schedule onsite calibration',
     'Book technician visit to St. Mary’s Hospital site.',
     'todo')
) AS t(customer_id, title, body, status)
ON CONFLICT DO NOTHING;
