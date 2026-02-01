# Claude Skills for Raspberry Pi Telemetry

Two comprehensive Claude skills for working with the Raspberry Pi telemetry logger system.

## Skills Included

### 1. raspberry-pi-telemetry.skill
Work with Raspberry Pi telemetry logger systems that collect battery, CPU, and process metrics into SQLite databases.

**Triggers when you need to:**
- Set up or configure telemetry logging on Raspberry Pi
- Analyze power consumption and battery drain patterns
- Build ML models to predict power usage
- Query or visualize telemetry data
- Troubleshoot systemd services
- Work with power_supply sysfs interfaces
- Extract training datasets from time-series telemetry

**Key Features:**
- Quick start guides for installation and service setup
- Battery/power data analysis with mAh/min calculations
- ML workflow guidance (feature engineering, data export)
- Process analysis queries (CPU hotspots, correlations)
- Common troubleshooting patterns
- Automated scripts for battery analysis and feature extraction

**Bundled Resources:**
- `references/schema.md` - Complete database schema documentation
- `references/queries.md` - Advanced SQL query patterns
- `scripts/analyze_battery.py` - Automated battery analysis tool
- `scripts/export_features.py` - ML feature extraction utility

### 2. sqlite-analysis.skill
Analyze and query SQLite databases, particularly time-series telemetry data.

**Triggers when you need to:**
- Explore SQLite database schemas
- Write complex analytical queries
- Optimize query performance
- Debug data quality issues
- Generate reports from SQLite data
- Work with time-series analysis patterns
- Use window functions, aggregations, and correlations

**Key Features:**
- Schema discovery and inspection commands
- Time-series query patterns (window functions, gaps, trends)
- Analytical patterns (correlation, percentiles, outliers)
- Performance optimization techniques
- Data quality checks
- Export and reporting workflows
- Advanced patterns (recursive CTEs, JSON support)

**Bundled Resources:**
- `references/window-functions.md` - Comprehensive window function guide

## Installation

### In Claude.ai Web Interface

1. Navigate to your Claude conversation
2. Click the **Skills** icon in the bottom toolbar
3. Click **Add Skill**
4. Upload the `.skill` files:
   - `raspberry-pi-telemetry.skill`
   - `sqlite-analysis.skill`
5. The skills are now available in all your conversations

### Using the Skills

Once installed, the skills automatically trigger based on your requests. For example:

**Raspberry Pi Telemetry:**
- "How do I set up the telemetry logger on my Raspberry Pi?"
- "Show me how to analyze battery drain patterns"
- "Help me export ML training data from my telemetry database"
- "My telemetry service won't start, how do I debug it?"

**SQLite Analysis:**
- "How do I find gaps in my time-series data?"
- "Write a query to calculate rolling averages"
- "Help me optimize this slow SQLite query"
- "Show me how to detect outliers in my measurements"

Claude will automatically read the appropriate skill documentation and use the bundled scripts/references as needed.

## Skill Contents Overview

### raspberry-pi-telemetry Structure
```
raspberry-pi-telemetry/
├── SKILL.md                          # Main skill documentation
├── scripts/
│   ├── analyze_battery.py            # Automated battery analysis
│   └── export_features.py            # ML feature extraction
└── references/
    ├── schema.md                     # Complete database schema
    └── queries.md                    # Advanced query patterns
```

### sqlite-analysis Structure
```
sqlite-analysis/
├── SKILL.md                          # Main skill documentation
└── references/
    └── window-functions.md           # Window functions reference
```

## Example Use Cases

### 1. Battery Life Analysis
```
User: "Analyze my battery drain over the last 24 hours"

Claude: [Triggers raspberry-pi-telemetry skill]
[Uses analyze_battery.py script]
[Generates comprehensive battery report]
```

### 2. Power Prediction Model
```
User: "Export features for training a power consumption model"

Claude: [Triggers raspberry-pi-telemetry skill]
[Uses export_features.py with lag features]
[Creates CSV with process aggregates and time-lagged values]
```

### 3. Complex Time-Series Query
```
User: "Find processes that correlate with high power usage"

Claude: [Triggers both skills]
[Uses sqlite-analysis for window functions]
[Uses raspberry-pi-telemetry for schema knowledge]
[Writes optimized correlation query]
```

### 4. Data Quality Check
```
User: "Check for gaps in my telemetry sampling"

Claude: [Triggers sqlite-analysis skill]
[Uses gap detection pattern]
[Identifies missing data periods]
```

## Skill Features

### Progressive Disclosure
Skills use a three-level loading system:
1. **Metadata** (name + description) - Always in context
2. **SKILL.md body** - Loaded when skill triggers
3. **Bundled resources** - Loaded only when Claude needs them

This ensures efficient use of context while maintaining access to deep knowledge.

### Executable Scripts
Scripts can be executed directly without loading into context, making them token-efficient for repetitive tasks.

### Reference Documentation
Detailed references are loaded on-demand when Claude determines they're needed for the current task.

## Tips for Best Results

1. **Be specific about your goal:**
   - Good: "Show me battery drain patterns when Firefox is running"
   - Better: "Compare average mAh/min drain with and without Firefox in the process list"

2. **Mention file types or systems:**
   - "Analyze this telemetry.db file" → Triggers skills automatically
   - "I have a SQLite database" → Triggers sqlite-analysis

3. **Ask for examples:**
   - "Show me an example query for X" → Claude uses bundled query patterns
   - "What's the best way to Y?" → Claude references optimization guides

4. **Request script execution:**
   - "Run the battery analysis script on my database"
   - "Export features with lag periods 1, 6, 12"

## Technical Requirements

### For Raspberry Pi Telemetry
- Raspberry Pi OS (or compatible Linux)
- Python 3.7+
- SQLite 3.25+ (for window functions)
- `python3-psutil` (from apt)
- Optional: UPS HAT or PMIC with power_supply sysfs interface

### For SQLite Analysis
- SQLite 3.25+ (for window functions, PERCENTILE_CONT)
- SQLite 3.38+ (for JSON functions)
- Basic SQL knowledge helpful but not required

## Troubleshooting

### Skills Not Triggering
- Make sure you've uploaded both `.skill` files
- Try being more explicit: "Use the raspberry-pi-telemetry skill to..."
- Mention specific terms: "telemetry database", "battery drain", "SQLite analysis"

### Scripts Not Available
- Scripts are automatically available when skills are installed
- Claude can execute them directly or read them for modification
- If needed, ask: "Can you show me the analyze_battery.py script?"

### Missing Features
- Check which SQLite version you're using: `sqlite3 --version`
- Some features (window functions, JSON) require newer SQLite versions
- Skills will suggest alternatives if features unavailable

## Contributing

These skills were created using Claude's skill-creator framework. To modify or extend:

1. Unzip the `.skill` file (it's a renamed ZIP)
2. Edit `SKILL.md` or add new resources
3. Repackage with the skill-creator tools
4. Upload the new `.skill` file

## Version Information

- **raspberry-pi-telemetry**: v1.0.0
- **sqlite-analysis**: v1.0.0
- **Compatible with**: Claude Sonnet 4.5 and later
- **Created**: January 2026

## License

These skills are provided as-is for use with Claude. The bundled scripts are MIT licensed (matching the original telemetry logger project).

---

**Questions?** Ask Claude! These skills are designed to answer questions about themselves and guide you through using the telemetry system effectively.
