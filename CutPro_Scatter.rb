# ============================================
# CutPro Scatter v3.7.0 — Final Production Version
# - Simplest veneer detection (any blue = veneer)
# - Auto-calculates length by part type
# - Pure length, no width needed
# ============================================

require 'sketchup.rb'
require 'net/http'
require 'uri'
require 'json'

module CutPro
  module Scatter
    
    VERSION = '3.7.0'
    BACKEND_URL = 'http://localhost:5000'
    MIN_PANEL_FACE_MM = 30
    MAX_3D_THICKNESS_MM = 50
    
    # ============================================
    # 🎨 BLUE COLOR DETECTION
    # ============================================
    def self.is_blue?(color)
      return false if color.nil?
      
      r = color.red
      g = color.green
      b = color.blue
      
      # Blue: high B channel, low R and G
      return b > 180 && r < 150 && g < 200
    end
    
    # ============================================
    # 🎯 SIMPLE VENEER DETECTION
    # If ANY face is blue → veneer needed
    # ============================================
    def self.has_any_blue?(part)
      begin
        faces = part.entities.grep(Sketchup::Face)
        
        faces.each do |face|
          if face.material && is_blue?(face.material.color)
            return true
          end
          if face.back_material && is_blue?(face.back_material.color)
            return true
          end
        end
        
        return false
      rescue => e
        return false
      end
    end
    
    # ============================================
    # 🎯 CALCULATE VENEER LENGTH BY PART TYPE
    # ============================================
    def self.calc_veneer_length(part_type, big_dim, mid_dim)
      """
      Calculate the total edge length that needs veneer:
        - DOOR/DRAWER: 4 sides = 2 × (width + height)
        - SHELF/SIDE_PANEL: 1 side (front edge) = width
      """
      case part_type
      when "DOOR", "DRAWER"
        return 2 * (big_dim + mid_dim)
      when "SHELF", "SIDE_PANEL", "TALL_PANEL", "TOE_KICK", "COUNTERTOP"
        return big_dim
      else
        # Default: 4 sides
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
      
      # Check file saved
      original_path = model.path
      if original_path.nil? || original_path.empty?
        UI.messagebox(
          "⚠️ Please SAVE your model first!\n\n" +
          "File → Save As → give it a name\n\n" +
          "Then run CutPro again."
        )
        return
      end
      
      # Check backend
      backend_ok = check_backend
      
      if !backend_ok
        result = UI.messagebox(
          "⚠️ CutPro backend is NOT running!\n\n" +
          "Start it first:\n" +
          "  CutPro_Launcher.bat\n\n" +
          "Continue anyway?",
          MB_YESNO
        )
        return if result != IDYES
      end
      
      # Permission
      permission = UI.messagebox(
        "📦 CutPro Scatter v#{VERSION}\n\n" +
        "This will:\n" +
        "  1. Create a SAFE copy of your file\n" +
        "  2. Detect BLUE painted parts (veneer)\n" +
        "  3. Scatter all parts\n" +
        "  4. Send to CutPro\n" +
        "  5. Open browser\n\n" +
        "🎨 Paint any face of a part BLUE\n" +
        "   and it will get veneer.\n\n" +
        "Continue?",
        MB_YESNO
      )
      return if permission != IDYES
      
      # Create numbered copy
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
        "📁 Original (SAFE):\n" +
        "   #{File.basename(original_path)}\n\n" +
        "📄 Copy will be created as:\n" +
        "   #{File.basename(copy_path)}\n\n" +
        "Continue?",
        MB_YESNO
      )
      return if confirm != IDYES
      
      # Save original then copy
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
      
      # Collect parts
      UI.messagebox("🔍 Scanning model for parts...")
      
      all_parts = []
      collect_all_parts(model.entities, all_parts, 0)
      
      if all_parts.empty?
        UI.messagebox("❌ No parts found!")
        return
      end
      
      # Scatter + veneer detection
      model.start_operation("CutPro Scatter", true)
      
      grid_columns = 10
      spacing = 5000.mm
      
      parts_data = []
      scattered_count = 0
      veneer_count = 0
      non_veneer_count = 0
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
          
          # Filters
          next if mid_dim < MIN_PANEL_FACE_MM
          next if big_dim < MIN_PANEL_FACE_MM
          next if thin_dim > MAX_3D_THICKNESS_MM
          next if big_dim > 3000
          next if mid_dim > 2500 && big_dim > 2500
          
          # Detect part type
          part_type = detect_part_type(big_dim, mid_dim, thin_dim)
          next if part_type == 'SOLID_PIECE'
          
          # 🎯 CHECK IF PART IS BLUE (SIMPLE!)
          has_veneer = has_any_blue?(part)
          
          veneer_sides = 0
          veneer_length_mm = 0
          
          if has_veneer
            veneer_sides = 4  # Default
            veneer_length_mm = calc_veneer_length(part_type, big_dim, mid_dim)
            veneer_count += 1
            total_blue_mm += veneer_length_mm
          else
            non_veneer_count += 1
          end
          
          # Position in grid
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
          
          # Rename
          veneer_tag = has_veneer ? "_V" : ""
          part.name = "PART_#{scattered_count + 1}_#{part_type}#{veneer_tag}"
          
          # Collect
          parts_data << {
            width: big_dim,
            height: mid_dim,
            depth: thin_dim,
            material: '18mm Birch Plywood',
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
      puts "🎨 Veneer parts:  #{veneer_count}"
      puts "⚪ Non-veneer:    #{non_veneer_count}"
      puts "📏 Total length:  #{total_blue_m}m"
      puts "=" * 60
      
      # Send to backend
      sent = false
      if backend_ok && parts_data.length > 0
        sent = send_to_backend(parts_data)
      end
      
      if sent
        sleep(0.5)
        open_web_app()
      end
      
      if sent
        UI.messagebox(
          "🎉 SUCCESS!\n\n" +
          "📊 Panels scattered: #{scattered_count}\n" +
          "🎨 Veneer parts:    #{veneer_count}\n" +
          "📏 Total length:    #{total_blue_m}m\n\n" +
          "🌐 Browser opening now..."
        )
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
        http.open_timeout = 3
        http.read_timeout = 3
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
        http.open_timeout = 5
        http.read_timeout = 30
        
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
  
  submenu.add_item('🎨 How to Mark Veneer') {
    UI.messagebox(
      "🎨 HOW TO MARK VENEER\n\n" +
      "1. Select any face of a part\n" +
      "2. Paint it BLUE\n" +
      "3. CutPro will detect it\n\n" +
      "WHAT HAPPENS:\n" +
      "  DOOR → veneer on 4 sides\n" +
      "  SHELF → veneer on 1 side\n" +
      "  DRAWER → veneer on 4 sides\n\n" +
      "Just paint one face blue\n" +
      "and CutPro does the rest!"
    )
  }
  
  submenu.add_item('🔍 Check CutPro Status') {
    if CutPro::Scatter.check_backend
      UI.messagebox("✅ CutPro backend is RUNNING")
    else
      UI.messagebox("❌ CutPro backend NOT running")
    end
  }
  
  submenu.add_item('🌐 Open CutPro Website') {
    CutPro::Scatter.open_web_app
  }
  
  submenu.add_separator
  
  submenu.add_item('ℹ️ About CutPro') {
    UI.messagebox("📐 CutPro v#{CutPro::Scatter::VERSION}")
  }
  
  file_loaded(__FILE__)
end

puts "=" * 60
puts "✅ CutPro v#{CutPro::Scatter::VERSION} loaded"
puts "🎨 Simple blue detection"
puts "=" * 60