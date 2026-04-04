-- ═══════════════════════════════════════════════
--  DietFocus – Supabase Database Schema
--  Paste this into Supabase → SQL Editor → Run
-- ═══════════════════════════════════════════════

-- Weight logs table (one entry per day)
CREATE TABLE IF NOT EXISTS weight_logs (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date        DATE NOT NULL UNIQUE,
    weight_kg   DECIMAL(5,2) NOT NULL,
    notes       TEXT DEFAULT '',
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Meal logs table (up to 2 per day)
CREATE TABLE IF NOT EXISTS meal_logs (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date          DATE NOT NULL,
    meal_number   INTEGER NOT NULL CHECK (meal_number IN (1, 2)),
    description   TEXT NOT NULL,
    protein_g     DECIMAL(6,1) DEFAULT 0,
    carbs_g       DECIMAL(6,1) DEFAULT 0,
    fat_g         DECIMAL(6,1) DEFAULT 0,
    calories      INTEGER DEFAULT 0,
    image_url     TEXT,
    analysis_raw  TEXT,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Fasting logs table (optional daily check-in)
CREATE TABLE IF NOT EXISTS fasting_logs (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date            DATE NOT NULL UNIQUE,
    completed_fast  BOOLEAN DEFAULT FALSE,
    first_meal_time TIME,
    notes           TEXT DEFAULT '',
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_weight_logs_date ON weight_logs(date DESC);
CREATE INDEX IF NOT EXISTS idx_meal_logs_date   ON meal_logs(date DESC);
CREATE INDEX IF NOT EXISTS idx_fasting_logs_date ON fasting_logs(date DESC);

-- Auto-update updated_at on weight_logs
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER weight_logs_updated_at
    BEFORE UPDATE ON weight_logs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Enable Row Level Security (recommended)
ALTER TABLE weight_logs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE meal_logs    ENABLE ROW LEVEL SECURITY;
ALTER TABLE fasting_logs ENABLE ROW LEVEL SECURITY;

-- Allow all operations via anon key (single-user app)
CREATE POLICY "Allow all" ON weight_logs  FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON meal_logs    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON fasting_logs FOR ALL USING (true) WITH CHECK (true);
