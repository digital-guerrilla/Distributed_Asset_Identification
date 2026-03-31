# DAID — Seed demo data across 4 running nodes
# Run standalone (nodes must already be up): .\examples\seed-data.ps1
# Or: called automatically by examples\run-nodes.ps1

param(
    [int]$WaitSeconds = 0   # extra seconds to wait before seeding (0 = seed immediately)
)

if ($WaitSeconds -gt 0) {
    Write-Host "Waiting $WaitSeconds seconds for nodes to be ready..." -ForegroundColor Yellow
    Start-Sleep -Seconds $WaitSeconds
}

function Post-Asset {
    param([string]$Port, [string]$Key, [hashtable]$Body)
    try {
        $json = $Body | ConvertTo-Json -Depth 10
        $resp = Invoke-RestMethod -Method Post `
            -Uri "http://localhost:$Port/v1/assets" `
            -Headers @{ "x-api-key" = $Key; "Content-Type" = "application/json" } `
            -Body $json -ErrorAction Stop
        Write-Host "  [+] $($resp.id)" -ForegroundColor Green
    } catch {
        Write-Host "  [!] Failed on port $Port`: $_" -ForegroundColor Red
    }
}

# ── Alpha — Industrial Tools (Acme Industrial) ────────────────────────────
Write-Host ""
Write-Host "=== Alpha :8001 (Industrial Tools — Acme Industrial) ===" -ForegroundColor Cyan

Post-Asset 8001 "alpha-key" @{
    authority_data = @{
        name = "Heavy-Duty Torque Wrench"
        manufacturer = "Acme Industrial"
        model_number = "TW-5500-HD"
        serial_number = "SN-001-2024"
        hardware_revision = "Rev C"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="Acme Industrial"; ModelLabel="TW-5500-HD"; ProductionYear="2024" }
            Pset_Warranty = @{ WarrantyIdentifier="WR-TW5500"; WarrantyStartDate="2024-01-01"; WarrantyPeriod="P2Y" }
        }
        documents = @(
            @{ type="installation_manual"; url="https://docs.acme.example/tw5500/install.pdf"; mime_type="application/pdf"; language="en" }
            @{ type="ce_declaration"; url="https://docs.acme.example/tw5500/ce.pdf"; mime_type="application/pdf" }
        )
    }
    metadata = @{
        description = "Professional 1/2-inch drive torque wrench, 30-250 Nm"
        category = "industrial-tools"
        sku = "ACM-TW5500-HD"
        tags = @("torque","wrench","hand-tool","iso9001")
        attributes = @{ torque_min_nm=30; torque_max_nm=250; drive_size="1/2 inch"; weight_kg=2.4 }
    }
}

Post-Asset 8001 "alpha-key" @{
    authority_data = @{
        name = "Precision Digital Caliper"
        manufacturer = "Acme Industrial"
        model_number = "DC-200-PRO"
        hardware_revision = "Rev A"
        firmware_version = "1.3.0"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="Acme Industrial"; ModelLabel="DC-200-PRO"; ProductionYear="2023" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P10Y" }
        }
        documents = @(
            @{ type="user_manual"; url="https://docs.acme.example/dc200/manual.pdf"; mime_type="application/pdf"; language="en" }
        )
    }
    metadata = @{
        description = "0-200mm digital caliper, 0.01mm resolution, IP54 rated"
        category = "measurement-tools"
        sku = "ACM-DC200-PRO"
        gtin = "0614141999996"
        tags = @("caliper","measurement","precision")
        attributes = @{ range_mm=200; resolution_mm=0.01; ip_rating="IP54" }
    }
}

Post-Asset 8001 "alpha-key" @{
    authority_data = @{
        name = "Pneumatic Angle Grinder"
        manufacturer = "Acme Industrial"
        model_number = "AG-115-P"
        serial_number = "SN-AG-7742"
        hardware_revision = "Rev B"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="Acme Industrial"; ModelLabel="AG-115-P"; ProductionYear="2024" }
            Pset_MaintenanceStrategy = @{ MaintenanceStrategy="ConditionBased"; PlannedMaintenanceInterval="P6M" }
        }
    }
    metadata = @{
        description = "115mm pneumatic angle grinder, 12000 RPM, 1/4-inch BSP inlet"
        category = "power-tools"
        sku = "ACM-AG115-P"
        tags = @("grinder","pneumatic","power-tool")
        attributes = @{ disc_diameter_mm=115; max_rpm=12000; air_inlet="1/4 BSP"; weight_kg=1.8 }
    }
}

# ── Beta — HVAC & Building Systems (ClimaTech Systems) ───────────────────
Write-Host ""
Write-Host "=== Beta :8002 (HVAC & Building Systems — ClimaTech Systems) ===" -ForegroundColor Cyan

Post-Asset 8002 "beta-key" @{
    authority_data = @{
        name = "Smart Thermostat Controller"
        manufacturer = "ClimaTech Systems"
        model_number = "CTS-900-WIFI"
        firmware_version = "4.2.1"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="ClimaTech Systems"; ModelLabel="CTS-900-WIFI"; ProductionYear="2025" }
            Pset_Warranty = @{ WarrantyIdentifier="CT-WR-900"; WarrantyPeriod="P3Y" }
        }
        documents = @(
            @{ type="installation_guide"; url="https://climatech.example/cts900/install.pdf"; mime_type="application/pdf" }
            @{ type="api_reference"; url="https://climatech.example/cts900/api.html"; mime_type="text/html" }
        )
        schema_org = @{ "@type"="Product"; brand=@{ "@type"="Brand"; name="ClimaTech" } }
    }
    metadata = @{
        description = "Wi-Fi smart thermostat with 7-day programming, app control and energy reporting"
        category = "hvac-controls"
        sku = "CTS-900W"
        gtin = "5012345678900"
        tags = @("thermostat","smart-home","wifi","hvac")
        attributes = @{ connectivity="WiFi 2.4GHz"; display="3.5 inch colour touchscreen"; voltage_v=240; protocols=@("MQTT","REST") }
    }
}

Post-Asset 8002 "beta-key" @{
    authority_data = @{
        name = "Variable Speed Drive — 7.5 kW"
        manufacturer = "ClimaTech Systems"
        model_number = "VSD-075-3PH"
        serial_number = "VSD-2025-00412"
        hardware_revision = "Rev D"
        firmware_version = "3.0.5"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="ClimaTech Systems"; ModelLabel="VSD-075-3PH"; ProductionYear="2025" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P15Y"; MeanTimeBetweenFailure="87600h" }
            Pset_MaintenanceStrategy = @{ MaintenanceStrategy="Scheduled"; PlannedMaintenanceInterval="P1Y" }
        }
    }
    metadata = @{
        description = "7.5 kW three-phase variable speed drive, IP55, integrated EMC filter"
        category = "drives-motors"
        sku = "CTS-VSD075-3P"
        tags = @("vsd","drive","motor-control","industrial")
        attributes = @{ power_kw=7.5; phases=3; ip_rating="IP55"; input_voltage_v=400; frequency_hz=50 }
    }
}

Post-Asset 8002 "beta-key" @{
    authority_data = @{
        name = "Air Handling Unit — 10,000 m³/h"
        manufacturer = "ClimaTech Systems"
        model_number = "AHU-100-EC"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="ClimaTech Systems"; ModelLabel="AHU-100-EC"; ProductionYear="2024" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P20Y" }
            Pset_Warranty = @{ WarrantyPeriod="P2Y" }
        }
        documents = @(
            @{ type="commissioning_manual"; url="https://climatech.example/ahu100/commissioning.pdf"; mime_type="application/pdf" }
            @{ type="bim_model"; url="https://climatech.example/ahu100/model.ifc"; mime_type="application/octet-stream" }
        )
    }
    metadata = @{
        description = "EC-fan air handling unit, heat recovery 85%, 10,000 m³/h nominal airflow"
        category = "hvac-ahu"
        sku = "CTS-AHU100EC"
        tags = @("ahu","hvac","heat-recovery","ec-fan")
        attributes = @{ airflow_m3h=10000; heat_recovery_pct=85; fan_type="EC"; weight_kg=420 }
    }
}

# ── Gamma — Safety & Electrical (SafeGuard Pro) ───────────────────────────
Write-Host ""
Write-Host "=== Gamma :8003 (Safety & Electrical — SafeGuard Pro) ===" -ForegroundColor Cyan

Post-Asset 8003 "gamma-key" @{
    authority_data = @{
        name = "Arc Flash PPE Kit — Class 2"
        manufacturer = "SafeGuard Pro"
        model_number = "AF-KIT-C2-L"
        hardware_revision = "2024 Edition"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SafeGuard Pro"; ModelLabel="AF-KIT-C2-L"; ProductionYear="2024" }
            Pset_Warranty = @{ WarrantyPeriod="P5Y" }
        }
        documents = @(
            @{ type="safety_data_sheet"; url="https://safeguard.example/af-c2/sds.pdf"; mime_type="application/pdf" }
            @{ type="certification"; url="https://safeguard.example/af-c2/iec61482.pdf"; mime_type="application/pdf" }
        )
    }
    metadata = @{
        description = "IEC 61482-1-2 Class 2 arc flash kit: jacket, trousers, balaclava, face shield, gloves"
        category = "ppe-electrical"
        sku = "SGP-AFKIT-C2-L"
        tags = @("ppe","arc-flash","electrical-safety","iec61482")
        attributes = @{ arc_rating_cal_cm2=12; standard="IEC 61482-1-2 Class 2"; size="Large" }
    }
}

Post-Asset 8003 "gamma-key" @{
    authority_data = @{
        name = "Insulated Screwdriver Set — 7 Piece"
        manufacturer = "SafeGuard Pro"
        model_number = "ISD-SET-7"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SafeGuard Pro"; ModelLabel="ISD-SET-7"; ProductionYear="2023" }
        }
        documents = @(
            @{ type="certification"; url="https://safeguard.example/isd7/iec60900.pdf"; mime_type="application/pdf" }
        )
    }
    metadata = @{
        description = "1000V insulated screwdriver set, 7 piece, VDE certified, IEC 60900"
        category = "hand-tools-electrical"
        sku = "SGP-ISD-SET7"
        gtin = "4003773030303"
        tags = @("screwdriver","insulated","vde","1000v","iec60900")
        attributes = @{ pieces=7; max_voltage_v=1000; standard="IEC 60900 / VDE" }
    }
}

Post-Asset 8003 "gamma-key" @{
    authority_data = @{
        name = "Portable PAT Tester"
        manufacturer = "SafeGuard Pro"
        model_number = "PAT-3000-BT"
        firmware_version = "2.5.0"
        serial_number = "PAT-SN-20241188"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SafeGuard Pro"; ModelLabel="PAT-3000-BT"; ProductionYear="2024" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P7Y" }
            Pset_Warranty = @{ WarrantyPeriod="P2Y"; WarrantyIdentifier="SGP-WR-PAT3000" }
        }
        documents = @(
            @{ type="user_manual"; url="https://safeguard.example/pat3000/manual.pdf"; mime_type="application/pdf"; language="en" }
            @{ type="calibration_cert"; url="https://safeguard.example/pat3000/cal.pdf"; mime_type="application/pdf" }
        )
    }
    metadata = @{
        description = "Bluetooth portable appliance tester, auto-sequence, 2500V insulation test, cloud sync"
        category = "test-equipment"
        sku = "SGP-PAT3000BT"
        tags = @("pat-tester","electrical-testing","bluetooth","portable")
        attributes = @{ insulation_test_v=2500; connectivity="Bluetooth 5.0"; battery="Li-Ion 3000mAh"; display="2.8 inch LCD" }
    }
}

# ── Delta — Sensors & IoT (SensorEdge) ───────────────────────────────────
Write-Host ""
Write-Host "=== Delta :8004 (Sensors & IoT — SensorEdge) ===" -ForegroundColor Cyan

Post-Asset 8004 "delta-key" @{
    authority_data = @{
        name = "Industrial Temperature Sensor — PT100"
        manufacturer = "SensorEdge"
        model_number = "SE-PT100-4W"
        serial_number = "SE-2025-00091"
        hardware_revision = "Rev B"
        firmware_version = "1.0.2"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SensorEdge"; ModelLabel="SE-PT100-4W"; ProductionYear="2025" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P10Y" }
            Pset_Warranty = @{ WarrantyPeriod="P3Y" }
        }
        documents = @(
            @{ type="datasheet"; url="https://sensoredge.example/pt100-4w/datasheet.pdf"; mime_type="application/pdf" }
            @{ type="wiring_diagram"; url="https://sensoredge.example/pt100-4w/wiring.pdf"; mime_type="application/pdf" }
        )
    }
    metadata = @{
        description = "4-wire PT100 RTD temperature sensor, -50 to +250°C, 4-20mA output, IP67"
        category = "sensors-temperature"
        sku = "SE-PT100-4W-B"
        gtin = "8001234567890"
        tags = @("sensor","temperature","pt100","4-20ma","ip67","industrial")
        attributes = @{ range_min_c=-50; range_max_c=250; output="4-20mA"; accuracy_c=0.1; ip_rating="IP67"; connection="4-wire" }
    }
}

Post-Asset 8004 "delta-key" @{
    authority_data = @{
        name = "Wireless Vibration Monitor"
        manufacturer = "SensorEdge"
        model_number = "SE-VIB-WL2"
        firmware_version = "3.1.0"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SensorEdge"; ModelLabel="SE-VIB-WL2"; ProductionYear="2025" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P8Y" }
        }
        documents = @(
            @{ type="datasheet"; url="https://sensoredge.example/vib-wl2/datasheet.pdf"; mime_type="application/pdf" }
            @{ type="api_reference"; url="https://sensoredge.example/vib-wl2/api.html"; mime_type="text/html" }
        )
    }
    metadata = @{
        description = "Wireless MEMS vibration sensor for predictive maintenance, 3-axis, ISO 10816 alarm thresholds"
        category = "sensors-vibration"
        sku = "SE-VIB-WL2"
        tags = @("vibration","sensor","wireless","predictive-maintenance","iso10816")
        attributes = @{ axes=3; frequency_range_hz="1-10000"; protocol="LoRaWAN / Modbus"; battery_life_years=5; ip_rating="IP65" }
    }
}

Post-Asset 8004 "delta-key" @{
    authority_data = @{
        name = "Edge Gateway — Industrial IoT"
        manufacturer = "SensorEdge"
        model_number = "SE-GW-4G-EDGE"
        firmware_version = "5.0.1"
        serial_number = "GW-2025-10033"
        ifc_psets = @{
            Pset_ManufacturerTypeInformation = @{ Manufacturer="SensorEdge"; ModelLabel="SE-GW-4G-EDGE"; ProductionYear="2025" }
            Pset_ServiceLife = @{ ServiceLifeDuration="P10Y" }
            Pset_Warranty = @{ WarrantyPeriod="P3Y"; WarrantyIdentifier="SE-GW-WR-10033" }
            Pset_MaintenanceStrategy = @{ MaintenanceStrategy="RemoteFirmwareUpdate"; PlannedMaintenanceInterval="P1Y" }
        }
        documents = @(
            @{ type="quick_start"; url="https://sensoredge.example/gw4g/quickstart.pdf"; mime_type="application/pdf" }
            @{ type="api_reference"; url="https://sensoredge.example/gw4g/api.html"; mime_type="text/html"; language="en" }
            @{ type="ce_declaration"; url="https://sensoredge.example/gw4g/ce.pdf"; mime_type="application/pdf" }
        )
        schema_org = @{ "@type"="Product"; brand=@{ "@type"="Brand"; name="SensorEdge" } }
    }
    metadata = @{
        description = "4G/LTE industrial IoT edge gateway, 8-port RS485, dual Ethernet, Linux, Docker-ready"
        category = "iot-gateways"
        sku = "SE-GW4G-EDGE"
        gtin = "8009876543210"
        tags = @("gateway","iot","4g","lte","edge-computing","docker","modbus")
        attributes = @{ cellular="4G LTE Cat-4"; rs485_ports=8; ethernet_ports=2; os="Linux 5.15"; ram_gb=2; storage_gb=32; ip_rating="IP40" }
    }
}

Write-Host ""
Write-Host "Done! 12 demo products seeded across all 4 nodes." -ForegroundColor Green
