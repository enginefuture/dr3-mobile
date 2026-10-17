#import <UIKit/UIKit.h>

// Settings are selected before any Metal device or guest preload is created.
@interface LauncherViewController : UIViewController
@property (copy) void (^onPlay)(BOOL wide, BOOL hud, BOOL metalfx, BOOL lan);
- (instancetype)initWithWideAvailable:(BOOL)wide lanAvailable:(BOOL)lan ready:(BOOL)ready reason:(NSString *)reason;
@end
