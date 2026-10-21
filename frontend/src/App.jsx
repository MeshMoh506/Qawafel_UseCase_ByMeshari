import { useEffect, useState } from 'react'
import Summary from './pages/Summary.jsx'
import Figure from './pages/Figure.jsx'
import Method from './pages/Method.jsx'

// A tiny hash router: #/ (summary), #/figure/<key>, #/method
function useRoute() {
  const read = () => window.location.hash.replace(/^#/, '') || '/'
  const [route, setRoute] = useState(read())
  useEffect(() => {
    const on = () => {
      setRoute(read())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}

export default function App() {
  const route = useRoute()
  let page
  if (route.startsWith('/figure/')) page = <Figure figKey={decodeURIComponent(route.slice(8))} />
  else if (route === '/method') page = <Method />
  else page = <Summary />
  return (
    <>
      <nav className="topbar">
        <a href="#/" className="brand">Financing package review</a>
        <div>
          <a href="#/" className={route === '/' ? 'on' : ''}>Summary</a>
          <a href="#/method" className={route === '/method' ? 'on' : ''}>How this was checked</a>
        </div>
      </nav>
      <main>{page}</main>
      <footer>Sample data only. The business, bank and customers are made up.</footer>
    </>
  )
}
