"""Lookup tables: the API returns INSEE codes, Sales wants readable labels."""

# NAF rev.2 sections (letter returned by the API as `section_activite_principale`).
NAF_SECTIONS = {
    "A": "Agriculture", "B": "Mining", "C": "Manufacturing", "D": "Energy",
    "E": "Water & Waste", "F": "Construction", "G": "Retail & Wholesale",
    "H": "Transport & Logistics", "I": "Hospitality & Food", "J": "IT & Telecom",
    "K": "Finance & Insurance", "L": "Real Estate", "M": "Professional Services",
    "N": "Business Support", "O": "Public Administration", "P": "Education",
    "Q": "Health & Social", "R": "Arts & Leisure", "S": "Other Services",
    "T": "Households", "U": "Extraterritorial",
}

# NAF divisions = first 2 digits of the NAF code (e.g. "56.10A" -> "56").
NAF_DIVISIONS = {
    "01": "Crop and animal production", "02": "Forestry", "03": "Fishing",
    "10": "Food manufacturing", "11": "Beverages", "13": "Textiles", "14": "Clothing",
    "16": "Wood products", "18": "Printing", "20": "Chemicals", "22": "Rubber & plastics",
    "23": "Non-metallic minerals", "25": "Metal products", "26": "Electronics",
    "27": "Electrical equipment", "28": "Machinery", "31": "Furniture", "32": "Other manufacturing",
    "33": "Machinery repair & installation", "35": "Electricity & gas", "38": "Waste management",
    "41": "Building construction", "42": "Civil engineering", "43": "Specialised construction trades",
    "45": "Motor vehicle trade & repair", "46": "Wholesale trade", "47": "Retail trade",
    "49": "Land transport", "50": "Water transport", "51": "Air transport",
    "52": "Warehousing & logistics", "53": "Postal & courier", "55": "Accommodation",
    "56": "Restaurants & bars", "58": "Publishing", "59": "Film, video & music",
    "60": "Broadcasting", "61": "Telecommunications", "62": "Software & IT consulting",
    "63": "Information services", "64": "Financial services", "65": "Insurance",
    "66": "Auxiliary financial services", "68": "Real estate", "69": "Legal & accounting",
    "70": "Management consulting", "71": "Architecture & engineering", "72": "Scientific R&D",
    "73": "Advertising & market research", "74": "Other professional activities",
    "75": "Veterinary", "77": "Rental & leasing", "78": "Employment & staffing",
    "79": "Travel agencies", "80": "Security", "81": "Building services & landscaping",
    "82": "Office & business support", "84": "Public administration", "85": "Education",
    "86": "Human health", "87": "Residential care", "88": "Social work",
    "90": "Creative & performing arts", "93": "Sports & recreation",
    "94": "Membership organisations", "95": "Repair of computers & household goods",
    "96": "Other personal services (incl. hairdressing)",
}

# INSEE headcount brackets: code -> (label, minimum employees). None = unknown.
HEADCOUNT_BRACKETS = {
    "NN": ("No employees (non-employer)", 0), "00": ("0 employees", 0),
    "01": ("1-2", 1), "02": ("3-5", 3), "03": ("6-9", 6),
    "11": ("10-19", 10), "12": ("20-49", 20), "21": ("50-99", 50),
    "22": ("100-199", 100), "31": ("200-249", 200), "32": ("250-499", 250),
    "41": ("500-999", 500), "42": ("1000-1999", 1000), "51": ("2000-4999", 2000),
    "52": ("5000-9999", 5000), "53": ("10000+", 10000),
}

# Most common INSEE legal-form codes (`nature_juridique`).
LEGAL_FORMS = {
    "1000": "Entrepreneur individuel", "5202": "SNC", "5306": "SCS",
    "5385": "SELAS", "5410": "SARL nationale", "5485": "SELARL", "5498": "EURL",
    "5499": "SARL", "5505": "SA", "5599": "SA", "5710": "SAS", "5720": "SASU",
    "5785": "SELAS", "6540": "SCI", "6599": "Société civile", "9220": "Association",
}
