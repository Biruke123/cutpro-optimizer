# ============================================
# CutPro Scatter v3.9.0 — Color Matching Edition
# - Fetches user's material colors from cloud
# - Matches any SketchUp color to nearest material
# - Blue face = veneer
# ============================================

require 'sketchup.rb'
require 'net/http'
require 'uri'
require 'json'

module CutPro
  module Scatter

    VERSION = '3.9.0'
    BACKEND_URL = 'https://cutpro-optimizer.onrender.com'
    MIN_PANEL_FACE_MM = 30
    MAX_3D_THICKNESS_MM = 50
    COLOR_MATCH_TOLERANCE = 60

    # ============================================
    # 🎨 BLUE COLOR DETECTION
    # ============================================
    def self.is_blue?(color)
      return false if color.nil?
      r = color.red
      g = color.green
      b = color.blue
      return b > 180 && r < 150 && g < 200
    end

    # ============================================
    # 🎨 FETCH USER'S MATERIAL COLORS FROM CLOUD
    # ============================================
    def self.fetch_material_colors
      begin
        uri = URI.parse("#{BACKEND_URL}/api/material-colors")
        http = Net::HTTP.new(uri.host, uri.port)
        http.use_ssl = (uri.scheme == 'https')
        http.verify_mode = OpenSSL::SSL::VERIFY_NONE if uri.scheme == 'https'
        http.open_timeout = 10
        http.read_timeout = 15

        request = Net::HTTP::Get.new(uri.path)
        response = http.request(request)

        if response.code == '200'
          data = JSON.parse(response.body)
          materials = data['materials'] || []
          puts "✅ Loaded #{materials.length} materials from cloud"
          return materials
        else
          puts "⚠️ Could not fetch materials (HTTP #{response.code}) — using defaults"
          return default_materials
        end
      rescue => e
        puts "⚠️ Material fetch failed: #{e.message} — using defaults"
        return default_materials
      end
    end

    # ============================================
    # 📦 FALLBACK DEFAULT MATERIALS
    # ============================================
    def self.default_materials
      [
        { 'id' => 'oak',      'name' => 'Oak',      'shades' => [{ 'label' => 'Base', 'hex' => '#BE805B' }] },
        { 'id' => 'walnut',   'name' => 'Walnut',   'shades' => [{ 'label' => 'Base', 'hex' => '#6B3F23' }] },
        { 'id' => 'teak',     'name' => 'Teak',     'shades' => [{ 'label' => 'Base', 'hex' => '#A5762D' }] },
        { 'id' => 'mahogany', 'name' => 'Mahogany', 'shades' => [{ 'label' => 'Base', 'hex' => '#7B2D1F' }] },
        { 'id' => 'cherry',   'name' => 'Cherry',   'shades' => [{ 'label' => 'Base', 'hex' => '#9B4A2C' }] },
        { 'id' => 'pine',     'name' => 'Pine',     'shades' => [{ 'label' => 'Base', 'hex' => '#E5C88C' }] },
        { 'id' => 'birch',    'name' => 'Birch',    'shades' => [{ 'label' => 'Base', 'hex' => '#D9C6A3' }] },
        { 'id' => 'mdf',      'name' => 'MDF',      'shades' => [{ 'label' => 'Base', 'hex' => '#C4A88E' }] },
        { 'id' => 'melamine', 'name' => 'Melamine', 'shades' => [{ 'label' => 'Base', 'hex' => '#E8DCC4' }] },
        { 'id' => 'uv_board', 'name' => 'UV Board', 'shades' => [{ 'label' => 'Base', 'hex' => '#F8F9FA' }] },
        { 'id' => 'plywood',  'name' => 'Plywood',  'shades' => [{ 'label' => 'Base', 'hex' => '#C99A6E' }] },
        { 'id' => 'bamboo',   'name' => 'Bamboo',   'shades' => [{ 'label' => 'Base', 'hex' => '#D4B57A' }] },
        { 'id' => 'mdf_gray', 'name' => 'MDF Gray', 'shades' => [{ 'label' => 'Base', 'hex' => '#9E9E9E' }] }
      ]
    end

    # ============================================
    # 🔧 HEX → RGB
    # ============================================
    def self.hex_to_rgb(hex)
      h = hex.gsub('#', '')
      {
        'r' => h[0..1].to_i(16),
        'g' => h[2..3].to_i(16),
        'b' => h[4..5].to_i(16)
      }
    end

    # ============================================
    # 🔧 COLOR DISTANCE (Euclidean RGB)
    # ============================================
    def self.color_distance(r1, g1, b1, r2, g2, b2)
      Math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
    end

    # ============================================
    # 🎯 DETECT MATERIAL BY COLOR MATCHING
    # ============================================
    def self.detect_material(part, materials)
      color = nil

      if part.respond_to?(:material) && part.material
        c = part.material.color
        color = { 'r' => c.red, 'g' => c.green, 'b' => c.blue }
      end

      if color.nil? && part.respond_to?(:entities)
        begin
          faces = part.entities.grep(Sketchup::Face)
          faces.each do |face|
            if face.material && !is_blue?(face.material.color)
              c = face.material.color
              color = { 'r' => c.red, 'g' => c.green, 'b' => c.blue }
              break
            end
          end
        rescue
        end
      end

      if color.nil?
        puts "  ⚠️ Part has no material — defaulting to MDF"
        return 'MDF'
      end

      best_match = nil
      best_distance = Float::INFINITY

      materials.each do |material|
        (material['shades'] || []).each do |shade|
          next if shade['hex'].nil?
          rgb = hex_to_rgb(shade['hex'])
          dist = color_distance(
            color['r'], color['g'], color['b'],
            rgb['r'], rgb['g'], rgb['b']
          )
          if dist < best_distance
            best_distance = dist
            best_match = material['name']
          end
        end
      end

      if best_distance.nil? || best_distance > COLOR_MATCH_TOLERANCE
        puts "  ⚠️ RGB(#{color['r']},#{color['g']},#{color['b']}) no match (dist #{best_distance.round(1)}) — MDF"
        return 'MDF'
      end

      puts "  ✅ RGB(#{color['r']},#{color['g']},#{color['b']}) → #{best_match} (dist #{best_distance.round(1)})"
      best_match
    end

    # ============================================
    # 🎯 SIMPLE VENEER DETECTION
    # ============================================
    def self.has_any_blue?(part)
      begin
        faces = part.entities.grep(Sketchup::Face)
        faces.each do |face|
          return true if face.material && is_blue?(face.material.color)
          return true if face.back_material && is_blue?(face.back_material.color)
        end
        return false
      rescue
        return false
      end
    end

    # ============================================
    # 🎯 CALCULATE VENEER LENGTH BY PART TYPE
    # ============================================
    def self.calc_veneer_length(part_type, big_dim, mid_dim)
      case part_type
      when "DOOR", "DRAWER"
        return 2 * (big_dim + mid_dim)
      when "SHELF", "SIDE_PANEL", "TALL_PANEL", "TOE_KICK", "COUNTERTOP"
        return big_dim
      else
        return 2 * (big_dim + mid_dim)
      end
    end

    # ============================================
    # OPEN CUTPRO WEBSITE
    # ============================================
    def self.open_web_app
      UI.openURL(BACKEND_URL)
      puts "🌐 Opened CutPro: #{BACKEND_URL}"
    end

    # ============================================
    # MAIN FUNCTION
    # ============================================
    def self.scatter_and_send
      model = Sketchup.active_model

      original_path = model.path
      if original_path.nil? || original_path.empty?
        UI.messagebox("⚠️ Please SAVE your model first!\n\nFile → Save As → give it a name\n\nThen run CutPro again.")
        return
      end

      backend_ok = check_backend
      if !backend_ok
        result = UI.messagebox(
          "⚠️ Cannot reach CutPro cloud!\n\n" +
          "Check your internet connection.\n\n" +
          "Expected server:\n#{BACKEND_URL}\n\nContinue anyway?",
          MB_YESNO
        )
        return if result != IDYES
      end

      # Fetch materials
      puts "🎨 Loading material colors from cloud..."
      user_materials = fetch_material_colors
      puts "   #{user_materials.length} materials loaded"

      permission = UI.messagebox(
        "📦 CutPro Scatter v#{VERSION}\n\n" +
        "This will:\n" +
        "  1. Create a SAFE copy of your file\n" +
        "  2. Load your material colors (#{user_materials.length} materials)\n" +
        "  3. Detect BLUE painted parts (veneer)\n" +
        "  4. Match colors to materials\n" +
        "  5. Scatter all parts\n" +
        "  6. Send to CutPro\n" +
        "  7. Open browser\n\n" +
        "🎨 Paint any face BLUE → veneer\n" +
        "🎨 Other colors match your materials\n\n" +
        "Continue?",
        MB_YESNO
      )
      return if permission != IDYES

      dir = File.dirname(original_path)
      base = File.basename(original_path, '.skp')

      copy_num = 1
      copy_path = nil
      loop do
        candidate = File.join(dir, "#{base}_scattered_#{copy_num}.skp")
        if !File.exist?(candidate)
          copy_path = candidate
          break
        end
        copy_num += 1
      end

      confirm = UI.messagebox(
        "📁 Original (SAFE):\n   #{File.basename(original_path)}\n\n" +
        "📄 Copy will be created as:\n   #{File.basename(copy_path)}\n\nContinue?",
        MB_YESNO
      )
      return if confirm != IDYES

      model.save(original_path) if model.modified?
      result = model.save(copy_path)

      if result == false
        UI.messagebox("❌ Failed to create copy!")
        return
      end

      puts "=" * 60
      puts "✅ SAFE COPY CREATED"
      puts "Working: #{File.basename(copy_path)}"
      puts "=" * 60

      UI.messagebox("🔍 Scanning model for parts...")

      all_parts = []
      collect_all_parts(model.entities, all_parts, 0)

      if all_parts.empty?
        UI.messagebox("❌ No parts found!")
        return
      end

      model.start_operation("CutPro Scatter", true)

      grid_columns = 10
      spacing = 5000.mm

      parts_data = []
      scattered_count = 0
      veneer_count = 0
      non_veneer_count = 0
      material_counts = Hash.new(0)
      total_blue_mm = 0

      all_parts.each_with_index do |part, index|
        begin
          bbox = part.bounds
          next if bbox.nil? || bbox.empty?

          width_mm = bbox.width.to_mm.round(1)
          height_mm = bbox.height.to_mm.round(1)
          depth_mm = bbox.depth.to_mm.round(1)

          sorted_dims = [width_mm, height_mm, depth_mm].sort
          thin_dim = sorted_dims[0]
          mid_dim = sorted_dims[1]
          big_dim = sorted_dims[2]

          next if mid_dim < MIN_PANEL_FACE_MM
          next if big_dim < MIN_PANEL_FACE_MM
          next if thin_dim > MAX_3D_THICKNESS_MM
          next if big_dim > 3000
          next if mid_dim > 2500 && big_dim > 2500

          part_type = detect_part_type(big_dim, mid_dim, thin_dim)
          next if part_type == 'SOLID_PIECE'

          has_veneer = has_any_blue?(part)

          veneer_sides = 0
          veneer_length_mm = 0

          if has_veneer
            veneer_sides = 4
            veneer_length_mm = calc_veneer_length(part_type, big_dim, mid_dim)
            veneer_count += 1
            total_blue_mm += veneer_length_mm
          else
            non_veneer_count += 1
          end

          material = detect_material(part, user_materials)
          material_counts[material] += 1

          row = scattered_count / grid_columns
          col = scattered_count % grid_columns

          target_x = col * spacing
          target_y = row * spacing
          target_z = 0

          current_center = bbox.center
          target_point = Geom::Point3d.new(target_x, target_y, target_z)
          translation = target_point - current_center
          transform = Geom::Transformation.translation(translation)

          if part.is_a?(Sketchup::Group) || part.is_a?(Sketchup::ComponentInstance)
            part.transform!(transform)
          end

          veneer_tag = has_veneer ? "_V" : ""
          part.name = "PART_#{scattered_count + 1}_#{part_type}#{veneer_tag}"

          parts_data << {
            width: big_dim,
            height: mid_dim,
            depth: thin_dim,
            material: material,
            label: part_type.gsub('_', ' '),
            qty: 1,
            veneer_edges: veneer_sides,
            veneer_length_mm: veneer_length_mm,
            has_veneer: has_veneer
          }

          scattered_count += 1

        rescue => e
          puts "⚠️ Skipped part #{index}: #{e.message}"
          next
        end
      end

      model.commit_operation
      model.save(copy_path)

      total_blue_m = (total_blue_mm / 1000.0).round(2)

      puts ""
      puts "=" * 60
      puts "✅ SCATTER COMPLETE"
      puts "=" * 60
      puts "Total panels:     #{scattered_count}"
      material_counts.each { |mat, count| puts "  #{mat}: #{count}" }
      puts "🎨 Veneer parts:  #{veneer_count}"
      puts "📏 Total length:  #{total_blue_m}m"
      puts "=" * 60

      sent = false
      if backend_ok && parts_data.length > 0
        sent = send_to_backend(parts_data)
      end

      if sent
        sleep(0.5)
        open_web_app()
      end

      if sent
        summary = "🎉 SUCCESS!\n\n"
        summary += "📊 Panels scattered: #{scattered_count}\n"
        material_counts.each { |mat, count| summary += "  • #{mat}: #{count}\n" }
        summary += "🎨 Veneer parts: #{veneer_count}\n"
        summary += "📏 Total length: #{total_blue_m}m\n\n"
        summary += "🌐 Browser opening now..."
        UI.messagebox(summary)
      else
        UI.messagebox("✅ Panels scattered: #{scattered_count}")
      end
    end

    # ============================================
    # HELPERS
    # ============================================

    def self.collect_all_parts(entities, collection, depth)
      return if depth > 20
      entities.each do |entity|
        begin
          if entity.is_a?(Sketchup::Group)
            collection << entity
            collect_all_parts(entity.entities, collection, depth + 1)
          elsif entity.is_a?(Sketchup::ComponentInstance)
            collection << entity
            collect_all_parts(entity.definition.entities, collection, depth + 1)
          end
        rescue
          next
        end
      end
    end

    def self.detect_part_type(big_dim, mid_dim, thin_dim)
      return "SOLID_PIECE" if thin_dim > 50

      if big_dim > 1500 && mid_dim > 400 && mid_dim < 700
        return "SIDE_PANEL"
      elsif big_dim > 1500 && mid_dim > 300
        return "TALL_PANEL"
      elsif big_dim > 500 && mid_dim > 500 && (big_dim / mid_dim.to_f) < 1.3
        return "DOOR"
      elsif big_dim < 700 && mid_dim < 700
        return "DRAWER"
      elsif big_dim > 300
        return "SHELF"
      else
        return "SMALL_PART"
      end
    end

    def self.check_backend
      begin
        uri = URI.parse("#{BACKEND_URL}/api/status")
        http = Net::HTTP.new(uri.host, uri.port)
        http.use_ssl = (uri.scheme == 'https')
        http.verify_mode = OpenSSL::SSL::VERIFY_NONE if uri.scheme == 'https'
        http.open_timeout = 15
        http.read_timeout = 20
        response = http.get(uri.path)
        response.code == '200'
      rescue
        false
      end
    end

    def self.send_to_backend(parts_data)
      begin
        uri = URI.parse("#{BACKEND_URL}/api/parts-from-sketchup")
        http = Net::HTTP.new(uri.host, uri.port)
        http.use_ssl = (uri.scheme == 'https')
        http.verify_mode = OpenSSL::SSL::VERIFY_NONE if uri.scheme == 'https'
        http.open_timeout = 15
        http.read_timeout = 60

        request = Net::HTTP::Post.new(uri.path)
        request['Content-Type'] = 'application/json'
        request.body = { parts: parts_data }.to_json

        response = http.request(request)
        puts "📥 Response: #{response.code}"
        response.code == '200'
      rescue => e
        puts "❌ Send failed: #{e.message}"
        false
      end
    end

  end
end

# ============================================
# MENU
# ============================================
unless file_loaded?(__FILE__)
  submenu = UI.menu('Plugins').add_submenu('📐 CutPro')

  submenu.add_item('🚀 Scatter & Send to CutPro') {
    CutPro::Scatter.scatter_and_send
  }

    submenu.add_separator

  submenu.add_item('🧪 Apply Test Colors to Selection') {
    model = Sketchup.active_model
    selection = model.selection

    if selection.empty?
      UI.messagebox("⚠️ Select some parts first (groups/components).")
    else
      materials = CutPro::Scatter.fetch_material_colors
      if materials.empty?
        UI.messagebox("❌ Could not load materials from CutPro.")
      else
        # Map of test materials to apply
        test_map = {
          'Oak' => materials.find { |m| m['name'] == 'Oak' },
          'MDF' => materials.find { |m| m['name'] == 'MDF' },
          'UV Board' => materials.find { |m| m['name'] == 'UV Board' },
          'Walnut' => materials.find { |m| m['name'] == 'Walnut' },
          'Melamine' => materials.find { |m| m['name'] == 'Melamine' }
        }

        # Cycle through test colors
        keys = test_map.keys.compact
        if keys.empty?
          UI.messagebox("❌ No test materials found in your palette.")
        else
          model.start_operation("Apply Test Colors", true)
          selection.each_with_index do |entity, i|
            mat_name = keys[i % keys.length]
            mat_data = test_map[mat_name]
            next unless mat_data
            next unless entity.is_a?(Sketchup::Group) || entity.is_a?(Sketchup::ComponentInstance)

            # Create or get SketchUp material
            hex = mat_data['shades'][0]['hex']
            rgb = CutPro::Scatter.hex_to_rgb(hex)

            skp_mat = model.materials[mat_name] || model.materials.add(mat_name)
            skp_mat.color = Sketchup::Color.new(rgb['r'], rgb['g'], rgb['b'])

            # Apply to entity
            entity.material = skp_mat

            # Also paint the faces
            if entity.respond_to?(:entities)
              entity.entities.grep(Sketchup::Face).each do |face|
                face.material = skp_mat
                face.back_material = skp_mat
              end
            end
          end
          model.commit_operation
          UI.messagebox("✅ Applied test colors to #{selection.length} part(s).\n\nColors cycle: #{keys.join(' → ')}")
        end
      end
    end
  }
  
  submenu.add_item('🎨 How to Mark Veneer') {
    UI.messagebox(
      "🎨 HOW TO MARK VENEER\n\n" +
      "1. Select any face of a part\n" +
      "2. Paint it BLUE\n" +
      "3. CutPro will detect it\n\n" +
      "MATERIAL DETECTION:\n" +
      "  Colors are matched to your materials\n" +
      "  Set colors in the CutPro website:\n" +
      "  Materials → Edit\n\n" +
      "  Default mappings:\n" +
      "  🟤 Brown → Oak\n" +
      "  ⚪ Gray → MDF\n" +
      "  ⚪ White → UV Board\n\n" +
      "  Or add your own in the web app!"
    )
  }

  submenu.add_item('🔍 Check CutPro Status') {
    if CutPro::Scatter.check_backend
      UI.messagebox("✅ CutPro cloud is reachable\n\n#{CutPro::Scatter::BACKEND_URL}")
    else
      UI.messagebox("❌ Cannot reach CutPro cloud\n\n#{CutPro::Scatter::BACKEND_URL}\n\nCheck your internet connection.")
    end
  }
    submenu.add_item('🎨 Check Material Colors') {
    materials = CutPro::Scatter.fetch_material_colors
    if materials.empty?
      UI.messagebox("❌ No materials loaded.\n\nCheck your internet connection.")
    else
      msg = "🎨 Your Material Palette\n\n"
      msg += "#{materials.length} materials loaded from CutPro:\n\n"
      materials.each do |m|
        shades = (m['shades'] || []).map { |s| s['hex'] }.join(', ')
        msg += "• #{m['name']}\n  #{shades}\n\n"
      end
      msg += "Paint these colors in SketchUp and CutPro will match them."
      UI.messagebox(msg)
    end
  }

  submenu.add_item('🌐 Open CutPro Website') {
    CutPro::Scatter.open_web_app
  }

  submenu.add_separator

  submenu.add_item('ℹ️ About CutPro') {
    UI.messagebox("📐 CutPro v#{CutPro::Scatter::VERSION}\n🎨 Color-matching edition")
  }

  file_loaded(__FILE__)
end

puts "=" * 60
puts "✅ CutPro v#{CutPro::Scatter::VERSION} loaded"
puts "🎨 Color matching enabled"
puts "=" * 60