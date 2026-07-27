from playwright.sync_api import sync_playwright
import time

def test_transient_activation():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # We will catch console messages
        messages = []
        page.on("console", lambda msg: messages.append(msg.text))
        
        # Create an HTML that tries to auto-launch an intent
        html = """
        <!DOCTYPE html>
        <html>
        <body>
        <script>
            console.log("Script starting");
            try {
                window.location.href = 'intent://open#Intent;package=com.tailscale.ipn;scheme=tailscale;end;';
                console.log("Assigned location.href");
            } catch(e) {
                console.log("Error: " + e);
            }
        </script>
        </body>
        </html>
        """
        
        # Load the HTML
        page.set_content(html)
        time.sleep(1) # wait for any async blocks
        
        print("Console Output:")
        for m in messages:
            print("-", m)
            
        browser.close()

if __name__ == "__main__":
    test_transient_activation()
