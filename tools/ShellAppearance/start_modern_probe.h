#pragma once

// Run the native GridView, ScrollViewer and diagnostics observer using the
// redesigned StartHome controls and slots present in the Windows templates.
static bool BF_ProbeModernStart(const std::filesystem::path& output,bool namedHeader) {
    const auto close=[](double a,double b){return std::abs(a-b)<1.5;};
    WNDCLASSW type{};type.lpfnWndProc=DefWindowProcW;type.hInstance=GetModuleHandleW(nullptr);
    type.lpszClassName=L"Windows.UI.Core.CoreWindow";RegisterClassW(&type);
    auto window=CreateWindowExW(0,type.lpszClassName,L"Redesigned Start layout",WS_POPUP,30,30,800,850,
                                nullptr,nullptr,type.hInstance,nullptr);
    Hosting::DesktopWindowXamlSource source;
    auto native=source.as<IDesktopWindowXamlSourceNative>();winrt::check_hresult(native->AttachToWindow(window));
    HWND child=nullptr;native->get_WindowHandle(&child);SetWindowPos(child,nullptr,0,0,800,850,SWP_NOZORDER|SWP_SHOWWINDOW);
    auto root=Markup::XamlReader::Load(LR"(<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="FrameRoot" Padding="12" MaxHeight="774" VerticalAlignment="Bottom">
      <Grid Name="AnimationRoot"><Rectangle Name="MaxHeightEnforcer" Height="750" Width="1" IsHitTestVisible="False"/>
        <Grid Name="MainMenu" Width="640">
          <Border Name="AcrylicBorder" Background="White"/>
          <Grid Name="MainContent" Margin="1">
            <Grid.RowDefinitions><RowDefinition Height="64"/><RowDefinition/><RowDefinition Height="64"/></Grid.RowDefinitions>
            <Button Name="SearchBoxToggleButton" Content="Windows Search" Height="40"/>
            <Frame Name="StartFrame" Grid.Row="1"/>
            <Grid Name="NavPanePlaceholder" Grid.Row="2" Height="40">
              <Button Name="UserTileButton" Content="账户" HorizontalAlignment="Left"/>
              <Button Name="PowerButton" Content="电源" HorizontalAlignment="Right"/>
            </Grid>
          </Grid>
        </Grid>
      </Grid>
    </Grid>)").as<Controls::Grid>();
    auto apps=Markup::XamlReader::Load(LR"(<GridView xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" Name="AllAppsGrid" SelectionMode="None" Padding="12,0,12,0" ScrollViewer.HorizontalScrollMode="Enabled" ScrollViewer.HorizontalScrollBarVisibility="Hidden">
        <GridView.ItemsPanel><ItemsPanelTemplate><ItemsWrapGrid Orientation="Horizontal" Margin="64,0,0,11" MaximumRowsOrColumns="4"/></ItemsPanelTemplate></GridView.ItemsPanel>
        <GridView.Header><Grid Name="TopLevelHeader">
          <Grid.RowDefinitions><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/><RowDefinition Height="Auto"/></Grid.RowDefinitions>
          <Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
          <Grid Margin="0,23,0,0"><TextBlock Name="PinnedListHeaderText" Text="Pinned" Margin="63,6,12,7"/></Grid>
          <Grid Grid.Column="1" Margin="0,23,0,0"><Button Name="ShowMorePinnedButton" Margin="0,0,52,0"><TextBlock Name="ShowMorePinnedButtonText" Text="Show more"/></Button></Grid>
          <ContentControl Name="StartMenuPinnedList" Grid.Row="1" Grid.ColumnSpan="2" Margin="0,9,0,8" HorizontalContentAlignment="Stretch" VerticalContentAlignment="Stretch" Height="240">
            <ContentControl.Template><ControlTemplate TargetType="ContentControl">
              <Grid Name="Root" Padding="32,0,4,0"><Grid.ColumnDefinitions><ColumnDefinition/><ColumnDefinition Width="24"/></Grid.ColumnDefinitions>
                <ContentPresenter Content="{TemplateBinding Content}"/>
              </Grid>
            </ControlTemplate></ContentControl.Template>
            <GridView Name="PinnedList" Height="240" SelectionMode="None" ScrollViewer.VerticalScrollMode="Disabled" ScrollViewer.VerticalScrollBarVisibility="Hidden">
              <GridView.ItemsPanel><ItemsPanelTemplate><ItemsWrapGrid Orientation="Horizontal" ItemWidth="96" ItemHeight="96"/></ItemsPanelTemplate></GridView.ItemsPanel>
            </GridView>
          </ContentControl>
          <Grid Name="TopLevelSuggestionsRoot" Grid.Row="2" Grid.ColumnSpan="2" Height="120"/>
          <Grid Name="AllListHeading" Grid.Row="3" Grid.ColumnSpan="2" Margin="0,23,0,0"><TextBlock Name="AllListHeadingText" Text="All" Margin="63,6,12,7" VerticalAlignment="Center"/></Grid>
        </Grid></GridView.Header>
    </GridView>)").as<Controls::GridView>();
    auto header=apps.Header().as<Controls::Grid>();
    auto pinHeading=header.Children().GetAt(0).as<Controls::Grid>();
    auto showMore=header.Children().GetAt(1).as<Controls::Grid>();
    auto pins=header.Children().GetAt(2).as<Controls::ContentControl>();
    if (namedHeader) {pinHeading.Name(L"PinnedListHeaderGrid");showMore.Name(L"ShowMorePinnedGrid");}
    auto recommendations=header.Children().GetAt(3).as<Controls::Grid>();
    auto appsHeading=header.Children().GetAt(4).as<Controls::Grid>();
    auto pinList=pins.Content().as<Controls::GridView>();
    auto page=BF_FindLayoutElement(root,L"StartFrame").as<Controls::Frame>();
    auto menu=BF_FindLayoutElement(root,L"MainMenu").as<Controls::Grid>();
    auto nav=BF_FindLayoutElement(root,L"NavPanePlaceholder").as<Controls::Grid>();
    auto search=BF_FindLayoutElement(root,L"SearchBoxToggleButton");
    page.Content(apps);
    for(int i=0;i<36;++i) {
        Controls::GridViewItem app;
        app.MinWidth(210);app.Height(40);app.Padding({12,0,12,0});
        app.Background(Media::SolidColorBrush(winrt::Windows::UI::Colors::Transparent()));
        Controls::Grid row;row.Width(536);
        Controls::TextBlock name;name.Text(L"Application "+std::to_wstring(i));row.Children().Append(name);
        app.Content(row);apps.Items().Append(app);
        Controls::GridViewItem pin;pin.Width(96);pin.Height(96);
        pin.Background(Media::SolidColorBrush(winrt::Windows::UI::Colors::Transparent()));
        Controls::Border icon;icon.Width(32);icon.Height(32);pin.Content(icon);
        pinList.Items().Append(pin);
    }
    source.Content(root);ShowWindow(window,SW_SHOW);
    auto settle=[&](int duration=140){
        const auto until=GetTickCount64()+duration;
        do {BF_ProbePump();root.UpdateLayout();Sleep(2);} while(GetTickCount64()<until);
    };
    settle();
    auto border=Media::VisualTreeHelper::GetChild(apps,0).as<Controls::Border>();
    auto original=border.Child().as<Controls::ScrollViewer>();
    const auto originalHorizontal=original.HorizontalScrollMode();
    const auto originalBar=original.HorizontalScrollBarVisibility();
    auto model=winrt::box_value(L"Start view model");header.DataContext(model);
    // A deferred part must leave the whole Start template usable until it
    // appears. Exercise the same retry path on both native header variants.
    header.Children().RemoveAt(0);
    bf_is_start_menu=true;
    MH_Initialize();
    if (!Wh_ModInit() || MH_EnableHook(MH_ALL_HOOKS)!=MH_OK) throw std::runtime_error("redesigned Start observer hooks");
    BF_RequestShellInitialization(window);
    settle(600);
    const bool waited=border.Child()==original && menu.Width()==640 &&
        Media::VisualTreeHelper::GetParent(pins)==header && search.Height()==40 && bf_init_state==2;
    header.Children().InsertAt(0,pinHeading);
    settle(500);

    auto wrapper=border.Child().try_as<Controls::Grid>();
    auto pinScroll=wrapper ? BF_FindLayoutElement(wrapper,L"SideBySidePinnedScrollViewer",1).try_as<Controls::ScrollViewer>() : nullptr;
    auto pinContent=pinScroll ? pinScroll.Content().try_as<Controls::Grid>() : nullptr;
    auto appPanel=apps.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>();
    auto pinnedPanel=pinList.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>();
    const auto appBox=BF_FooterBounds(original,menu),pinBox=BF_FooterBounds(pinScroll,menu);
    const auto appRow=apps.ContainerFromIndex(0).try_as<Controls::GridViewItem>();
    auto first=pinList.ContainerFromIndex(0).try_as<FrameworkElement>();
    auto fourth=pinList.ContainerFromIndex(3).try_as<FrameworkElement>();
    auto fifth=pinList.ContainerFromIndex(4).try_as<FrameworkElement>();
    const auto title=BF_FooterBounds(BF_FindLayoutElement(pinHeading,L"PinnedListHeaderText"),menu);
    const auto firstPin=BF_FooterBounds(first,menu),lastPin=BF_FooterBounds(fourth,menu),nextPin=BF_FooterBounds(fifth,menu);
    const auto rowBox=BF_FooterBounds(appRow,menu);
    auto hit=[&](const FrameworkElement& element,const wf::Rect& bounds) {
        auto point=menu.TransformToVisual(nullptr).TransformPoint({bounds.X+bounds.Width-4,bounds.Y+bounds.Height/2});
        for (auto result:Media::VisualTreeHelper::FindElementsInHostCoordinates(point,menu))
            if (IsVisualTreeDescendant(result,element)) return true;
        return false;
    };
    const bool lanes=pinContent && Media::VisualTreeHelper::GetParent(pinHeading)==pinContent &&
        Media::VisualTreeHelper::GetParent(showMore)==pinContent && Media::VisualTreeHelper::GetParent(pins)==pinContent &&
        Media::VisualTreeHelper::GetParent(appsHeading)==header && appBox.X>=18 && close(appBox.X+appBox.Width+10,pinBox.X) &&
        close(appBox.Y,pinBox.Y) && pinBox.X+pinBox.Width<=menu.ActualWidth() &&
        Media::VisualTreeHelper::GetParent(recommendations)==pinContent && recommendations.Visibility()==Visibility::Visible;
    const bool appsFit=appPanel && appPanel.MaximumRowsOrColumns()==1 && rowBox.Width>=appBox.Width-20 &&
        rowBox.X>=appBox.X-1 && rowBox.X+rowBox.Width<=appBox.X+appBox.Width+1;
    const bool four=pinnedPanel && pinnedPanel.MaximumRowsOrColumns()==4 && firstPin.Width>0 && lastPin.Width>0 &&
        close(firstPin.Y,lastPin.Y) && close(lastPin.X-firstPin.X,3*76) && close(nextPin.X,firstPin.X) && nextPin.Y>firstPin.Y &&
        lastPin.X+lastPin.Width<=pinBox.X+pinBox.Width+1 && close(title.X+title.Width/2,firstPin.X+firstPin.Width/2);
    const bool frameFits=close(menu.ActualWidth(),563) && close(menu.ActualHeight(),625) && close(root.ActualHeight(),649) &&
        nav.ActualWidth()>0 && BF_FooterBounds(nav,menu).Y+nav.ActualHeight()<=menu.ActualHeight();
    const bool scrolls=pinList.Items().Size()==36 && original.ScrollableHeight()>0 && pinScroll && pinScroll.ScrollableHeight()>0;
    const bool hitTargets=appRow && fourth && hit(appRow,rowBox) && hit(fourth,lastPin);
    const bool bound=showMore.DataContext()==model;
    unsigned clicks=0;
    auto button=BF_FindLayoutElement(showMore,L"ShowMorePinnedButton").as<Controls::Button>();
    auto click=button.Click(winrt::auto_revoke,[&](auto&&,auto&&){++clicks;});
    auto peer=BF_PanelPeer::CreatePeerForElement(button);
    if (peer) if (auto invoke=peer.GetPattern(winrt::Windows::UI::Xaml::Automation::Peers::PatternInterface::Invoke)
        .try_as<winrt::Windows::UI::Xaml::Automation::Provider::IInvokeProvider>()) invoke.Invoke();
    BF_AddStartSearchButton(nav);settle();
    const bool footerReady=bf_search_button_ready;
    const auto searchHeight=search.Height();const auto searchRow=Controls::Grid::GetRow(page);
    const bool searchFits=footerReady && searchHeight==0 && searchRow==0;
    apps.ItemsPanel(Markup::XamlReader::Load(LR"(<ItemsPanelTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"><ItemsWrapGrid Orientation="Horizontal" Margin="52,0,52,14" MaximumRowsOrColumns="1" ItemWidth="536"/></ItemsPanelTemplate>)").as<Controls::ItemsPanelTemplate>());
    settle();
    auto listPanel=apps.ItemsPanelRoot().try_as<Controls::ItemsWrapGrid>();
    const bool viewChanged=listPanel && listPanel!=appPanel && listPanel.MaximumRowsOrColumns()==1 &&
        close(listPanel.ItemWidth(),original.ViewportWidth()) && border.Child()==wrapper;
    Wh_ModUninit();MH_DisableHook(MH_ALL_HOOKS);MH_Uninitialize();settle();
    const bool restored=border.Child()==original && original.HorizontalScrollMode()==originalHorizontal &&
        original.HorizontalScrollBarVisibility()==originalBar && header.Children().Size()==5 && header.Children().GetAt(0)==pinHeading &&
        header.Children().GetAt(1)==showMore && header.Children().GetAt(2)==pins && recommendations.Visibility()==Visibility::Visible &&
        menu.Width()==640 && search.Height()==40 && Controls::Grid::GetRow(page)==1;
    auto report=std::ofstream(output/L"start-redesigned.json");
    const bool passed=waited && lanes && appsFit && four && frameFits && scrolls && hitTargets && bound && clicks==1 && searchFits && viewChanged && restored;
    report<<std::boolalpha<<"{\"passed\":"<<passed<<",\"waited\":"<<waited<<",\"lanes\":"<<lanes<<",\"app_rows\":"<<appsFit
          <<",\"four_pins\":"<<four<<",\"frame\":"<<frameFits<<",\"scrolls\":"<<scrolls<<",\"clicks\":"<<clicks
          <<",\"search\":"<<searchFits<<",\"view_changed\":"<<viewChanged<<",\"restored\":"<<restored<<",\"heading_binding\":"<<bound<<",\"hit_targets\":"<<hitTargets
          <<",\"app_width\":"<<appBox.Width<<",\"app_row_width\":"<<rowBox.Width
          <<",\"first_pin\":["<<firstPin.X<<","<<firstPin.Y<<","<<firstPin.Width<<"],\"fourth_pin\":["<<lastPin.X<<","<<lastPin.Y<<","<<lastPin.Width<<"]"
          <<",\"next_pin\":["<<nextPin.X<<","<<nextPin.Y<<","<<nextPin.Width<<"],\"pin_heading\":["<<title.X<<","<<title.Y<<","<<title.Width<<"]"
          <<",\"footer\":["<<footerReady<<","<<searchHeight<<","<<searchRow<<"]"
          <<",\"restoration\":["<<(border.Child()==original)<<","<<(original.HorizontalScrollMode()==originalHorizontal)<<","
          <<(original.HorizontalScrollBarVisibility()==originalBar)<<","<<header.Children().Size()<<","<<(header.Children().GetAt(0)==pinHeading)<<","
          <<(header.Children().GetAt(1)==showMore)<<","<<(header.Children().GetAt(2)==pins)<<","<<(recommendations.Visibility()==Visibility::Visible)<<","
          <<menu.Width()<<","<<search.Height()<<","<<Controls::Grid::GetRow(page)<<"],\"errors\":"<<bf_errors.load()<<",\"last_error\":"<<bf_last_error.load()<<"}";
    source.Close();DestroyWindow(window);
    return passed;
}
