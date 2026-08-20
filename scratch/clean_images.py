import os
from PIL import Image, ImageDraw, ImageFont

images_dir = r"c:\dev\Ticketing-Infrastructure-Security-Simulator\docs-html\assets\images"
image_files = [f for f in os.listdir(images_dir) if f.endswith(".jpg") and not f.startswith("media_")]

print(f"Cleaning THAITICKET references from {len(image_files)} images...")

for img_name in image_files:
    img_path = os.path.join(images_dir, img_name)
    with Image.open(img_path) as img:
        w, h = img.size
        edited = img.copy()
        draw = ImageDraw.Draw(edited)

        # 1. White header bar images with TTM THAITICKET MAJOR logo
        # checkout_details.jpg, checkout_payment_methods.jpg, performance_date_selection.jpg, payment_3ds_qr.jpg
        if img_name in ["checkout_details.jpg", "checkout_payment_methods.jpg", "performance_date_selection.jpg", "payment_3ds_qr.jpg"]:
            # White rectangle over top header logo center (w*0.35 to w*0.65, y: 0 to h*0.075)
            draw.rectangle([w * 0.35, 0, w * 0.65, int(h * 0.08)], fill=(255, 255, 255))
            
            # Optionally draw a clean neutral "TEST TICKET" badge in place of logo
            # Draw red TTM box + TEST TICKET text
            red_box = [int(w * 0.42), int(h * 0.015), int(w * 0.45), int(h * 0.055)]
            draw.rectangle(red_box, fill=(225, 29, 72))
            draw.text((int(w * 0.425), int(h * 0.025)), "TTM", fill=(255, 255, 255))
            draw.text((int(w * 0.46), int(h * 0.022)), "TEST TICKET", fill=(30, 41, 59))

        # 2. stealth_bot_dashboard.jpg
        if img_name == "stealth_bot_dashboard.jpg":
            # Mask out "ThaiTicketMajor" text with dark background color #111827
            draw.rectangle([int(w * 0.16), int(h * 0.168), int(w * 0.28), int(h * 0.19)], fill=(17, 24, 39))
            draw.text((int(w * 0.165), int(h * 0.17)), "TestTicket", fill=(16, 185, 129))

            draw.rectangle([int(w * 0.33), int(h * 0.705), int(w * 0.40), int(h * 0.735)], fill=(24, 32, 47))
            draw.text((int(w * 0.335), int(h * 0.71)), "TestTicket", fill=(16, 185, 129))

        edited.save(img_path, quality=95)
        print(f"Cleaned {img_name}")

print("All image cleaning completed successfully.")
